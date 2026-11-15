"""Air quality, water heater, lawn mower and remote.

Each is run through a REAL Home Assistant core (its state machine, its own entity
base classes and, for the water heater, its own checks on a mode and its own unit
conversion), because what a piston or an automation sees is what Home Assistant
announces, not what the entity holds. The claims being guarded:

  - a reading, mode or ability the original device never had is never invented;
  - an action does what its Home Assistant name says, and is announced;
  - a clone carries a device's SHAPE (which readings, which modes, which limits)
    and never its values;
  - a copy in either temperature unit starts inside its own limits.
"""

import logging
import tempfile

import pytest
from homeassistant.core import EVENT_STATE_CHANGED, CoreState, HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError

from conftest import run
from custom_components.virtual import clone
from custom_components.virtual.air_quality import (
    AIR_QUALITY_SCHEMA, DEFAULT_READINGS, VirtualAirQuality)
from custom_components.virtual.const import AIR_QUALITY_READINGS
from custom_components.virtual.lawn_mower import LAWN_MOWER_SCHEMA, VirtualLawnMower
from custom_components.virtual.remote import REMOTE_SCHEMA, VirtualRemote
from custom_components.virtual.water_heater import WATER_HEATER_SCHEMA, VirtualWaterHeater


def _real(domain, cls, schema, coro_factory):
    """Run `coro_factory(hass, make, events)` against a real Home Assistant."""
    async def go():
        hass = HomeAssistant(tempfile.mkdtemp())
        hass.set_state(CoreState.running)
        events = []
        hass.bus.async_listen(EVENT_STATE_CHANGED, callback(lambda ev: events.append(ev.data)))

        def make(**extra):
            entity = cls(schema({"name": "Thing", **extra}), False)
            entity.hass = hass
            entity.entity_id = f"{domain}.thing"
            entity._no_platform_reported = True   # added by hand, not through a platform
            entity._create_state(entity._config)
            entity._update_attributes()
            entity.async_write_ha_state()
            return entity

        try:
            return await coro_factory(hass, make, events)
        finally:
            await hass.async_stop(force=True)
    return run(go())


def _state(hass, domain="x"):
    return hass.states.get(f"{domain}.thing")


# ── air quality ─────────────────────────────────────────────────────────────────

def _air(coro_factory):
    return _real("air_quality", VirtualAirQuality, AIR_QUALITY_SCHEMA, coro_factory)


def test_a_new_air_sensor_reports_the_default_readings_and_nothing_else():
    async def go(hass, make, events):
        make()
        return _state(hass, "air_quality")

    state = _air(go)
    shown = {k for k in state.attributes if k in AIR_QUALITY_READINGS}
    assert shown == set(DEFAULT_READINGS), "a reading nobody asked for was invented"
    assert state.state == "0.0", "the state is the fine-particle reading"


def test_the_state_is_the_fine_particle_reading():
    """Home Assistant defines an air quality entity's state as PM2.5."""
    async def go(hass, make, events):
        entity = make()
        entity.set_readings({"particulate_matter_2_5": 12.5, "particulate_matter_10": 30})
        entity.async_write_ha_state()
        return _state(hass, "air_quality")

    state = _air(go)
    assert state.state == "12.5"
    assert state.attributes["particulate_matter_10"] == 30


def test_a_reading_the_device_does_not_carry_is_refused_not_invented():
    async def go(hass, make, events):
        entity = make(readings=["particulate_matter_2_5"])
        with pytest.raises(ServiceValidationError):
            entity.set_readings({"ozone": 40})
        entity.async_write_ha_state()
        return _state(hass, "air_quality")

    state = _air(go)
    assert "ozone" not in state.attributes


def test_pm25_is_always_carried_because_it_is_the_state():
    async def go(hass, make, events):
        make(readings=["ozone"])
        return _state(hass, "air_quality")

    state = _air(go)
    assert "particulate_matter_2_5" in state.attributes and "ozone" in state.attributes


def test_a_reading_set_to_zero_is_shown_not_dropped():
    """0 is a reading. Treating it as 'absent' would hide a clean-air value."""
    async def go(hass, make, events):
        entity = make(readings=["ozone"])
        entity.set_readings({"ozone": 5})
        entity.set_readings({"ozone": 0})
        entity.async_write_ha_state()
        return _state(hass, "air_quality")

    assert _air(go).attributes["ozone"] == 0


def test_every_reading_changes_what_home_assistant_announces():
    async def go(hass, make, events):
        entity = make()
        events.clear()
        entity.set_readings({"air_quality_index": 80})
        entity.async_write_ha_state()
        return events

    events = _air(go)
    assert events and events[-1]["new_state"].attributes["air_quality_index"] == 80


def test_a_restart_keeps_the_readings():
    entity = VirtualAirQuality(
        AIR_QUALITY_SCHEMA({"name": "Thing", "readings": ["ozone"]}), False)
    entity._restore_state(
        State("air_quality.thing", "9.0", {"particulate_matter_2_5": 9.0, "ozone": 33.0}),
        entity._config)
    assert entity._values == {"particulate_matter_2_5": 9.0, "ozone": 33.0}


def test_the_schema_rejects_a_reading_home_assistant_does_not_have():
    import voluptuous as vol
    with pytest.raises(vol.Invalid):
        AIR_QUALITY_SCHEMA({"name": "Thing", "readings": ["radon"]})


# ── water heater ────────────────────────────────────────────────────────────────

def _heater(coro_factory):
    return _real("water_heater", VirtualWaterHeater, WATER_HEATER_SCHEMA, coro_factory)


def test_a_new_water_heater_starts_inside_its_own_limits():
    async def go(hass, make, events):
        make()
        return _state(hass, "water_heater")

    state = _heater(go)
    low, high = state.attributes["min_temp"], state.attributes["max_temp"]
    assert low <= state.attributes["temperature"] <= high
    assert state.state == "eco"
    assert state.attributes["operation_list"] == ["off", "eco", "electric", "performance"]


def test_a_fahrenheit_copy_starts_inside_its_limits_not_at_a_celsius_number():
    """Home Assistant converts a native-unit value for display. A Fahrenheit heater
    started at 50 (the Celsius default) would read as 10 C, far below its own limits."""
    async def go(hass, make, events):
        make(temperature_unit="°F", min_temp=110, max_temp=140)
        return _state(hass, "water_heater")

    state = _heater(go)
    # What Home Assistant shows is in ITS unit (Celsius here): the heater's own
    # 110 to 140 F is about 43 to 60 C, and the target must sit in that range.
    low, high = state.attributes["min_temp"], state.attributes["max_temp"]
    assert low <= state.attributes["temperature"] <= high, (low, state.attributes["temperature"], high)


@pytest.mark.parametrize("unit, low, high", [("°F", 130, 150), ("°C", 60, 80)])
def test_a_start_outside_the_clones_own_limits_moves_into_them(unit, low, high):
    """The usual start (120 F, 50 C) is outside these limits; leaving it there is a
    target the heater itself would refuse."""
    async def go(hass, make, events):
        entity = make(temperature_unit=unit, min_temp=low, max_temp=high)
        return entity._attr_native_target_temperature if hasattr(
            entity, "_attr_native_target_temperature") else entity._attr_target_temperature

    target = _heater(go)
    assert low <= target <= high, (unit, low, target, high)


def test_the_mode_menu_is_checked_by_home_assistant_so_a_mode_off_it_is_refused():
    async def go(hass, make, events):
        entity = make(operation_list=["off", "eco"])
        with pytest.raises(ServiceValidationError):
            await entity.async_handle_set_operation_mode("turbo")
        await entity.async_handle_set_operation_mode("off")
        return _state(hass, "water_heater")

    assert _heater(go).state == "off"


def test_turning_off_then_on_returns_to_the_mode_it_was_in():
    async def go(hass, make, events):
        entity = make(initial_value="performance")
        await entity.async_turn_off()
        off = entity.current_operation
        await entity.async_turn_on()
        return off, entity.current_operation

    off, back = _heater(go)
    assert off == "off" and back == "performance"


def test_away_mode_is_reported_on_and_off():
    async def go(hass, make, events):
        entity = make()
        seen = [_state(hass, "water_heater").attributes["away_mode"]]
        await entity.async_turn_away_mode_on()
        seen.append(_state(hass, "water_heater").attributes["away_mode"])
        await entity.async_turn_away_mode_off()
        seen.append(_state(hass, "water_heater").attributes["away_mode"])
        return seen

    assert _heater(go) == ["off", "on", "off"]


def test_setting_the_target_and_the_current_temperature():
    async def go(hass, make, events):
        entity = make()
        await entity.async_set_temperature(temperature=55)
        entity.set_current_temperature(41)
        entity.async_write_ha_state()
        return _state(hass, "water_heater")

    state = _heater(go)
    assert state.attributes["temperature"] == 55
    assert state.attributes["current_temperature"] == 41


def test_a_clone_with_features_but_no_mode_menu_does_not_advertise_one():
    """Offering a mode dropdown with nothing in it errors the moment it is used."""
    async def go(hass, make, events):
        make(supported_features=1 | 2)     # target + operation mode, no list given
        return _state(hass, "water_heater")

    state = _heater(go)
    assert not state.attributes.get("operation_list")
    assert state.attributes["supported_features"] & 2 == 0, "the menu feature is still advertised"


def test_building_and_announcing_a_water_heater_logs_no_deprecation(caplog):
    async def go(hass, make, events):
        entity = make(temperature_unit="°F")
        await entity.async_set_temperature(temperature=120)
        return _state(hass, "water_heater")

    with caplog.at_level(logging.DEBUG):
        _heater(go)
    assert not [r for r in caplog.records if "deprecat" in r.getMessage().lower()]


# ── lawn mower ──────────────────────────────────────────────────────────────────

def _mower(coro_factory):
    return _real("lawn_mower", VirtualLawnMower, LAWN_MOWER_SCHEMA, coro_factory)


def test_each_mower_action_reaches_its_state():
    async def go(hass, make, events):
        entity = make()
        seen = [_state(hass, "lawn_mower").state]
        for action in (entity.async_start_mowing, entity.async_pause, entity.async_stop,
                       entity.async_start_mowing, entity.async_dock):
            await action()
            seen.append(_state(hass, "lawn_mower").state)
        return seen

    assert _mower(go) == ["docked", "mowing", "paused", "idle", "mowing", "docked"]


def test_set_activity_reaches_the_states_no_action_reaches():
    """A stuck mower is `error`, and no lawn mower action leads there."""
    async def go(hass, make, events):
        entity = make()
        seen = []
        for activity in ("error", "returning"):
            from custom_components.virtual.lawn_mower import _STATES
            entity.set_activity(_STATES[activity])
            seen.append(_state(hass, "lawn_mower").state)
        return seen

    assert _mower(go) == ["error", "returning"]


def test_the_default_mower_advertises_what_it_implements():
    async def go(hass, make, events):
        make()
        return _state(hass, "lawn_mower").attributes["supported_features"]

    bits = _mower(go)
    assert bits & 1 and bits & 2 and bits & 4, "start, pause and dock must be offered"


def test_a_restored_mower_keeps_its_state():
    entity = VirtualLawnMower(LAWN_MOWER_SCHEMA({"name": "Thing"}), False)
    entity._restore_state(State("lawn_mower.thing", "error", {}), entity._config)
    assert entity.activity.value == "error"


# ── remote ──────────────────────────────────────────────────────────────────────

def _remote(coro_factory):
    return _real("remote", VirtualRemote, REMOTE_SCHEMA, coro_factory)


def test_a_remote_with_activities_can_start_one_and_clears_it_on_off():
    async def go(hass, make, events):
        entity = make(activity_list=["Watch TV", "Music"])
        await entity.async_turn_on(activity="Music")
        on = _state(hass, "remote")
        await entity.async_turn_off()
        off = _state(hass, "remote")
        return on, off

    on, off = _remote(go)
    assert on.state == "on" and on.attributes["current_activity"] == "Music"
    assert off.state == "off" and off.attributes["current_activity"] is None


def test_an_activity_not_in_the_list_is_ignored():
    async def go(hass, make, events):
        entity = make(activity_list=["Watch TV"])
        await entity.async_turn_on(activity="Gaming")
        return _state(hass, "remote")

    state = _remote(go)
    assert state.state == "on" and state.attributes["current_activity"] is None


def test_a_remote_without_activities_does_not_advertise_the_feature():
    async def go(hass, make, events):
        make(supported_features=7)     # a clone that claims activities but names none
        return _state(hass, "remote").attributes["supported_features"]

    assert _remote(go) & 4 == 0, "an activity feature with no activities is an empty dropdown"


def test_send_command_is_recorded_and_announced_every_time_even_the_same_one():
    """Nothing real receives it, so the record IS the proof it arrived, and a repeat
    must still be a change Home Assistant announces (as the lock does)."""
    async def go(hass, make, events):
        entity = make()
        events.clear()
        for _ in range(3):
            await entity.async_send_command(["power", "volume_up"], device="tv")
        return events

    events = _remote(go)
    assert len(events) == 3, f"Home Assistant announced {len(events)} of 3 sends"
    last = events[-1]["new_state"].attributes
    assert [e["new_state"].attributes["sequence"] for e in events] == [1, 2, 3]
    assert last["last_action"] == "send_command"
    assert last["last_command"] == "power, volume_up" and last["last_device"] == "tv"


def test_learn_and_delete_are_recorded_too():
    async def go(hass, make, events):
        entity = make()
        await entity.async_learn_command(command=["mute"], device="tv")
        learned = dict(_state(hass, "remote").attributes)
        await entity.async_delete_command(command=["mute"], device="tv")
        return learned, dict(_state(hass, "remote").attributes)

    learned, deleted = _remote(go)
    assert learned["last_action"] == "learn_command" and learned["last_command"] == "mute"
    assert deleted["last_action"] == "delete_command" and deleted["sequence"] == 2


def test_a_command_sent_as_plain_text_is_recorded_the_same_way():
    async def go(hass, make, events):
        entity = make()
        await entity.async_send_command("power")
        return _state(hass, "remote").attributes["last_command"]

    assert _remote(go) == "power"


def test_a_restart_starts_the_record_afresh():
    entity = VirtualRemote(REMOTE_SCHEMA({"name": "Thing", "activity_list": ["A"]}), False)
    entity._create_state(entity._config)
    entity._sequence, entity._last_command = 1, "power"    # a record exists before the restore
    entity._restore_state(
        State("remote.thing", "on", {"current_activity": "A", "sequence": 9,
                                     "last_command": "x"}), entity._config)
    entity._update_attributes()
    assert entity.extra_state_attributes["sequence"] == 0
    assert entity.extra_state_attributes["last_command"] is None
    assert entity.current_activity == "A"


# ── cloning ─────────────────────────────────────────────────────────────────────

class _Units:
    temperature_unit = "°C"


class _Config:
    units = _Units()


class _Hass:
    config = _Config()


def _spec(domain, attrs):
    return clone.entity_spec(_Hass(), domain, None, attrs)


def test_an_air_clone_carries_which_readings_not_their_values():
    spec = _spec("air_quality", {"particulate_matter_2_5": 14.2, "ozone": 31,
                                 "friendly_name": "Air"})
    assert spec["readings"] == ["particulate_matter_2_5", "ozone"]
    assert "14.2" not in repr(spec) and "31" not in repr(spec), "a value was copied"
    AIR_QUALITY_SCHEMA({"name": "x", **spec})


def test_a_water_heater_clone_carries_its_shape_and_its_unit():
    spec = _spec("water_heater", {
        "supported_features": 15, "operation_list": ["off", "eco"],
        "min_temp": 110, "max_temp": 140, "target_temp_step": 1,
        "temperature": 120, "current_temperature": 118, "friendly_name": "Tank"})
    assert spec["operation_list"] == ["off", "eco"]
    assert (spec["min_temp"], spec["max_temp"], spec["target_temp_step"]) == (110, 140, 1)
    assert spec["supported_features"] == 15
    assert spec["temperature_unit"] == "°C"
    assert "temperature" not in spec and "current_temperature" not in spec, "state was copied"
    WATER_HEATER_SCHEMA({"name": "x", **spec})


def test_a_remote_clone_carries_its_activities_and_abilities():
    spec = _spec("remote", {"supported_features": 7, "activity_list": ["TV", "Music"],
                            "current_activity": "TV"})
    assert spec["activity_list"] == ["TV", "Music"] and spec["supported_features"] == 7
    assert "current_activity" not in spec
    REMOTE_SCHEMA({"name": "x", **spec})


def test_a_lawn_mower_clone_carries_its_abilities():
    spec = _spec("lawn_mower", {"supported_features": 7})
    assert spec == {"supported_features": 7}
    LAWN_MOWER_SCHEMA({"name": "x", **spec})


def test_all_four_can_be_cloned_and_are_provided_by_the_integration():
    from custom_components.virtual import VIRTUAL_PLATFORMS
    provided = {p.value for p in VIRTUAL_PLATFORMS}
    for domain in ("air_quality", "water_heater", "lawn_mower", "remote"):
        assert domain in clone.REPRODUCIBLE_DOMAINS, domain
        assert domain in provided, domain


def test_the_shared_current_temperature_action_only_serves_things_that_have_one():
    """`virtual.set_current_temperature` was a thermostat action; it now also serves a
    water heater. A lawn mower has no current temperature and must be told so."""
    from custom_components.virtual.climate import setup_services, SERVICE_SET_CURRENT_TEMPERATURE
    from custom_components.virtual.const import COMPONENT_DOMAIN

    async def go():
        hass = HomeAssistant(tempfile.mkdtemp())
        hass.set_state(CoreState.running)
        try:
            setup_services(hass)
            with pytest.raises(ServiceValidationError, match="no current temperature"):
                await hass.services.async_call(
                    COMPONENT_DOMAIN, SERVICE_SET_CURRENT_TEMPERATURE,
                    {"entity_id": "lawn_mower.thing", "value": 5}, blocking=True)
        finally:
            await hass.async_stop(force=True)

    run(go())


# ── restores, and the gaps a review found ───────────────────────────────────────

def test_a_restored_water_heater_keeps_its_target_mode_and_away_setting():
    async def go(hass, make, events):
        entity = make(operation_list=["off", "eco", "electric"])
        entity._restore_state(
            State("water_heater.thing", "electric",
                  {"temperature": 61, "current_temperature": 40, "away_mode": "on", "available": True}),
            entity._config)
        entity.async_write_ha_state()
        return _state(hass, "water_heater")

    state = _heater(go)
    assert state.state == "electric"
    assert state.attributes["temperature"] == 61
    assert state.attributes["current_temperature"] == 40
    assert state.attributes["away_mode"] == "on"


def test_a_restored_heater_in_the_other_unit_keeps_the_same_real_temperature():
    """Home Assistant stores temperatures in ITS unit; a heater declared in Fahrenheit
    keeps Fahrenheit. Taking the stored number as already Fahrenheit made 48.9 C read
    back as 9.4 C after a restart."""
    async def go(hass, make, events):
        entity = make(temperature_unit="°F", min_temp=90, max_temp=160)
        entity._restore_state(
            State("water_heater.thing", "eco", {"temperature": 48.9, "current_temperature": 46.1, "available": True}),
            entity._config)
        entity.async_write_ha_state()
        return _state(hass, "water_heater")

    state = _heater(go)
    assert abs(state.attributes["temperature"] - 48.9) < 0.2, state.attributes["temperature"]
    assert abs(state.attributes["current_temperature"] - 46.1) < 0.2


def test_a_restored_heater_with_nothing_stored_starts_inside_its_limits():
    async def go(hass, make, events):
        entity = make(operation_list=["eco"])
        entity._restore_state(State("water_heater.thing", "unavailable", {"available": True}), entity._config)
        entity.async_write_ha_state()
        return _state(hass, "water_heater")

    state = _heater(go)
    assert state.attributes["min_temp"] <= state.attributes["temperature"] <= state.attributes["max_temp"]
    assert state.state == "eco", "an unavailable mode falls back to one on the menu"


def test_set_temperature_can_carry_an_operation_mode_like_home_assistants_own_action():
    async def go(hass, make, events):
        entity = make(operation_list=["off", "eco", "performance"])
        await entity.async_set_temperature(temperature=52, operation_mode="performance")
        first = _state(hass, "water_heater")
        await entity.async_set_temperature(temperature=53, operation_mode="turbo")
        return first, _state(hass, "water_heater")

    first, second = _heater(go)
    assert first.state == "performance" and first.attributes["temperature"] == 52
    assert second.state == "performance", "a mode that is not on the menu is not taken"
    assert second.attributes["temperature"] == 53


def test_turning_a_heater_off_when_off_is_not_a_mode_changes_nothing_and_does_not_error():
    """Home Assistant reports a water heater's state as its mode, so with no `off`
    mode there is nothing for off to be. Documented in FORK_NOTES."""
    async def go(hass, make, events):
        entity = make(operation_list=["eco", "performance"])
        await entity.async_turn_off()
        return _state(hass, "water_heater").state

    assert _heater(go) == "eco"


def test_a_default_mower_advertises_stop_where_home_assistant_has_it():
    from homeassistant.components.lawn_mower import LawnMowerEntityFeature
    async def go(hass, make, events):
        make()
        return _state(hass, "lawn_mower").attributes["supported_features"]

    expected = 1 | 2 | 4 | int(getattr(LawnMowerEntityFeature, "STOP", 0))
    assert _mower(go) == expected


def test_a_restored_air_sensor_takes_pm25_from_its_state():
    entity = VirtualAirQuality(AIR_QUALITY_SCHEMA({"name": "Thing"}), False)
    entity._restore_state(State("air_quality.thing", "17.5", {}), entity._config)
    assert entity._values["particulate_matter_2_5"] == 17.5


def test_a_restored_unavailable_air_sensor_stays_unknown_not_zero():
    """Zero is a real reading. A sensor that was unavailable when Home Assistant
    stopped must not come back reporting clean air."""
    async def go(hass, make, events):
        entity = make()
        entity._restore_state(State("air_quality.thing", "unavailable", {}), entity._config)
        entity.async_write_ha_state()
        return entity, _state(hass, "air_quality")

    entity, state = _air(go)
    assert entity._values == {}
    assert not [k for k in state.attributes if k in AIR_QUALITY_READINGS]


def test_a_reading_that_is_not_a_finite_number_is_refused():
    import voluptuous as vol
    from custom_components.virtual.air_quality import SET_AIR_QUALITY_SCHEMA
    for bad in ("nan", "inf", float("nan"), "-inf"):
        with pytest.raises(vol.Invalid):
            SET_AIR_QUALITY_SCHEMA({"entity_id": "air_quality.thing", "ozone": bad})
    assert SET_AIR_QUALITY_SCHEMA({"entity_id": "air_quality.thing", "ozone": "4.5"})["ozone"] == 4.5


def test_a_starting_value_of_nan_starts_at_zero_not_nan():
    async def go(hass, make, events):
        make(initial_value="nan")
        return _state(hass, "air_quality")

    assert _air(go).state == "0.0"


def test_every_air_reading_can_be_set_from_the_services_screen():
    """The service accepts all of them, so the screen that lists its fields must too."""
    import pathlib, yaml
    services = yaml.safe_load(
        (pathlib.Path(clone.__file__).parent / "services.yaml").read_text(encoding="utf-8"))
    assert set(services["set_air_quality"]["fields"]) == set(AIR_QUALITY_READINGS)
    assert "set_current_temperature" in services


# ── the real setup path, and the services through Home Assistant's own registry ──
#
# A review found that nothing loaded a group containing these platforms or called the
# new `virtual.*` actions: every test built entities by hand. These run each platform's
# real `async_setup_entry` (schema, construction, services) from the data a group file
# produces, and call the actions through the real service registry.

from types import SimpleNamespace

import voluptuous as vol

from custom_components.virtual import air_quality as air_module
from custom_components.virtual import climate as climate_module
from custom_components.virtual import lawn_mower as mower_module
from custom_components.virtual import remote as remote_module
from custom_components.virtual import water_heater as heater_module
from custom_components.virtual.const import (
    ATTR_ENTITIES, ATTR_GROUP_NAME, COMPONENT_CONFIG, COMPONENT_DOMAIN)


class _Component:
    """What `hass.data[domain]` is in a running Home Assistant: it finds an entity by id."""
    def __init__(self):
        self.entities = {}

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)


def _loaded(module, domain, configs, coro_factory):
    """Run `coro_factory(hass, entities)` after the platform's real setup has built
    `entities` from `configs` (what a group file lists for this domain)."""
    async def go():
        hass = HomeAssistant(tempfile.mkdtemp())
        hass.set_state(CoreState.running)
        hass.data[COMPONENT_DOMAIN] = {"G": {ATTR_ENTITIES: {domain: configs}}}
        hass.data[COMPONENT_CONFIG] = {}
        component = hass.data[domain] = _Component()
        built = []
        try:
            await module.async_setup_entry(
                hass, SimpleNamespace(data={ATTR_GROUP_NAME: "G"}), built.extend)
            for entity in built:
                entity.hass = hass
                entity._no_platform_reported = True
                entity._create_state(entity._config)
                entity._update_attributes()
                entity.async_write_ha_state()
                component.entities[entity.entity_id] = entity
            return await coro_factory(hass, built)
        finally:
            await hass.async_stop(force=True)
    return run(go())


@pytest.mark.parametrize("module, domain, cls, service", [
    (air_module, "air_quality", VirtualAirQuality, "set_air_quality"),
    (heater_module, "water_heater", VirtualWaterHeater, "set_current_temperature"),
    (mower_module, "lawn_mower", VirtualLawnMower, "set_lawn_mower_activity"),
    (remote_module, "remote", VirtualRemote, None),
])
def test_setting_up_a_group_builds_the_entity_and_registers_its_action(module, domain, cls, service):
    async def go(hass, built):
        return ([type(e) for e in built], [e.entity_id for e in built],
                service is None or hass.services.has_service(COMPONENT_DOMAIN, service))

    kinds, ids, registered = _loaded(module, domain, [{"name": "Thing"}], go)
    assert kinds == [cls] and ids == [f"{domain}.thing"]
    assert registered, f"virtual.{service} was not registered by setting up the platform"


def test_set_air_quality_through_the_service_registry():
    async def go(hass, built):
        call = lambda data: hass.services.async_call(
            COMPONENT_DOMAIN, "set_air_quality", {"entity_id": "air_quality.thing", **data}, blocking=True)
        await call({"particulate_matter_2_5": "31", "ozone": 4})          # a string number is a number
        await hass.async_block_till_done()
        shown = hass.states.get("air_quality.thing")
        with pytest.raises(vol.Invalid):
            await call({"radon": 1})                                      # not a reading Home Assistant has
        with pytest.raises(vol.Invalid):
            await call({"ozone": "high"})
        with pytest.raises(ServiceValidationError):
            await call({"particulate_matter_10": 5})                      # not carried by this sensor
        return shown

    shown = _loaded(air_module, "air_quality",
                    [{"name": "Thing", "readings": ["ozone"]}], go)
    assert shown.state == "31.0" and shown.attributes["ozone"] == 4, \
        "the action must reach the state Home Assistant publishes, with no manual write"
    assert "particulate_matter_10" not in shown.attributes


def test_set_lawn_mower_activity_through_the_service_registry():
    async def go(hass, built):
        call = lambda activity: hass.services.async_call(
            COMPONENT_DOMAIN, "set_lawn_mower_activity",
            {"entity_id": "lawn_mower.thing", "activity": activity}, blocking=True)
        await call("error")
        error = hass.states.get("lawn_mower.thing").state
        with pytest.raises(vol.Invalid):
            await call("flying")
        return error, hass.states.get("lawn_mower.thing").state

    assert _loaded(mower_module, "lawn_mower", [{"name": "Thing"}], go) \
        == ("error", "error")


def test_the_shared_current_temperature_action_serves_a_water_heater():
    async def go(hass, built):
        await hass.services.async_call(
            COMPONENT_DOMAIN, "set_current_temperature",
            {"entity_id": "water_heater.thing", "value": 47}, blocking=True)
        await hass.async_block_till_done()
        return hass.states.get("water_heater.thing").attributes["current_temperature"]

    assert _loaded(heater_module, "water_heater", [{"name": "Thing"}], go) == 47


def test_services_yaml_describes_every_action_the_new_platforms_register():
    import pathlib, yaml
    services = yaml.safe_load(
        (pathlib.Path(clone.__file__).parent / "services.yaml").read_text(encoding="utf-8"))
    for name in (air_module.SERVICE_SET_AIR_QUALITY, mower_module.SERVICE_SET_ACTIVITY,
                 climate_module.SERVICE_SET_CURRENT_TEMPERATURE):
        assert name in services, f"{name} is registered but the services screen does not describe it"


# ── defaults, so a changed default is noticed ───────────────────────────────────

def _target(entity):
    return (entity.native_target_temperature if hasattr(entity, "native_target_temperature")
            else entity.target_temperature)


def test_a_default_water_heater_has_the_documented_abilities_and_celsius_limits():
    async def go(hass, make, events):
        entity = make()
        return entity.supported_features, entity._attr_min_temp, entity._attr_max_temp, _target(entity)

    features, low, high, target = _heater(go)
    assert features == 15 and (low, high, target) == (30.0, 70.0, 50.0)


def test_a_fahrenheit_water_heater_with_no_limits_gets_fahrenheit_ones():
    async def go(hass, make, events):
        entity = make(temperature_unit="°F")
        return entity._attr_min_temp, entity._attr_max_temp, _target(entity)

    assert _heater(go) == (90.0, 160.0, 120.0)


def test_a_target_temperature_step_reaches_the_entity():
    async def go(hass, make, events):
        return make(target_temp_step=2).target_temperature_step

    assert _heater(go) == 2


def test_a_remote_starts_off_with_learn_and_delete_and_honours_a_starting_value():
    async def go(hass, make, events):
        plain = make()
        on = make(initial_value="on")
        return plain.is_on, int(plain.supported_features), on.is_on

    assert _remote(go) == (False, 3, True)


def test_a_clone_that_left_out_the_activity_bit_does_not_get_it_back():
    async def go(hass, make, events):
        return int(make(supported_features=3, activity_list=["TV"]).supported_features)

    assert _remote(go) == 3


def test_a_restored_remote_keeps_its_power_and_a_listed_activity_only():
    entity = VirtualRemote(REMOTE_SCHEMA({"name": "Thing", "activity_list": ["TV"]}), False)
    entity._restore_state(State("remote.thing", "on", {"current_activity": "TV", "available": True}),
                          entity._config)
    assert entity.is_on is True and entity.current_activity == "TV"
    entity._restore_state(State("remote.thing", "off", {"current_activity": "Gone", "available": True}),
                          entity._config)
    assert entity.is_on is False and entity.current_activity is None


def test_a_starting_value_puts_the_mower_in_that_state():
    async def go(hass, make, events):
        return make(initial_value="mowing").activity.value

    assert _mower(go) == "mowing"


def test_air_readings_keep_pm25_first():
    async def go(hass, make, events):
        return make(readings=["ozone", "air_quality_index"])._carried

    assert _air(go)[0] == "particulate_matter_2_5"


def test_a_set_reading_is_announced_without_any_manual_write():
    async def go(hass, make, events):
        entity = make()
        events.clear()
        entity.set_readings({"air_quality_index": 61})
        await hass.async_block_till_done()
        return events

    events = _air(go)
    assert events and events[-1]["new_state"].attributes["air_quality_index"] == 61


def test_a_clone_of_all_eleven_readings_with_one_missing_keeps_the_other_ten_in_order():
    attrs = {name: 1.0 for name in AIR_QUALITY_READINGS}
    attrs["ozone"] = None
    spec = _spec("air_quality", attrs)
    assert spec["readings"] == [n for n in AIR_QUALITY_READINGS if n != "ozone"]
    AIR_QUALITY_SCHEMA({"name": "x", **spec})


def test_the_universal_remote_template_offers_activities():
    import json, pathlib
    templates = json.loads((pathlib.Path(clone.__file__).parent / "templates.json")
                           .read_text(encoding="utf-8"))
    remote_template = next(t for t in templates if t["name"] == "Universal remote")
    assert remote_template["entities"][0]["activity_list"]


# ── the registry deprecation fixes on a Home Assistant that iterates ids ────────

def test_the_device_list_looks_a_device_up_when_the_registry_iterates_ids():
    """Older Home Assistants yield ids when the registry is iterated; 2026.11 yields
    entries. This is the branch no container running 2026.10 or newer can reach."""
    from custom_components.virtual.panel import _all_devices
    entries = {"a": SimpleNamespace(id="a"), "b": SimpleNamespace(id="b")}
    registry = SimpleNamespace(devices=["a", "b"], async_get=entries.get)
    assert [d.id for d in _all_devices(registry)] == ["a", "b"]
    registry = SimpleNamespace(devices=list(entries.values()), async_get=lambda _: 1 / 0)
    assert [d.id for d in _all_devices(registry)] == ["a", "b"]


def test_a_phone_is_recognised_on_a_home_assistant_with_only_a_list_of_config_entries():
    """The older shape: a device with `config_entries` and no `config_entry_id`."""
    from custom_components.virtual import clone as clone_module
    domain = sorted(clone_module.PUSH_CONFIG_DOMAINS)[0]
    entries = {"e1": SimpleNamespace(domain=domain), "e2": SimpleNamespace(domain="demo")}
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_get_entry=entries.get))
    assert clone_module._is_phone(hass, SimpleNamespace(config_entries=["e2", "e1"])) is True
    assert clone_module._is_phone(hass, SimpleNamespace(config_entries=["e2"])) is False
