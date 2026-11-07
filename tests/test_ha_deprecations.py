"""Things Home Assistant has told this add-on to stop doing, kept fixed.

Each of these logged a warning at startup on Home Assistant 2026.11 and has a
removal date (the unit constants August 2027, the thermostat unit November 2027).
The camera one was flagged as disk work on the event loop. None of them changed
what a device does today, so a test that only looked at behaviour would pass
whether or not they came back: these look at both what the device does and
whether Home Assistant complains.
"""

import importlib
import logging
from pathlib import Path

import pytest

import custom_components.virtual.camera as cam
import custom_components.virtual.climate as climate_platform
import custom_components.virtual.number as number_platform
import custom_components.virtual.sensor as sensor_platform
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature

from conftest import run

# What the two units must read as on screen and in the history. Written out
# on purpose rather than taken from the enums the code now uses, so renaming
# the constant can never silently change what a CO2 sensor displays.
PPM = "ppm"
MICROGRAMS = "μg/m³"


def _complaints(caplog):
    return [r.getMessage() for r in caplog.records
            if "virtual" in r.getMessage() and "deprecated" in r.getMessage().lower()]


@pytest.mark.parametrize("module", [sensor_platform, number_platform])
def test_loading_a_unit_table_logs_no_deprecation(module, caplog):
    with caplog.at_level(logging.WARNING):
        importlib.reload(module)
    assert _complaints(caplog) == []


@pytest.mark.parametrize("device_class_enum, table", [
    (SensorDeviceClass, sensor_platform.UNITS_OF_MEASUREMENT),
    (NumberDeviceClass, number_platform.UNITS_OF_MEASUREMENT),
])
def test_gas_and_particle_sensors_keep_their_units(device_class_enum, table):
    assert table[device_class_enum.CO] == PPM
    assert table[device_class_enum.CO2] == PPM
    for name in ("NITROGEN_DIOXIDE", "NITROGEN_MONOXIDE", "NITROUS_OXIDE", "OZONE", "PM1", "PM10", "PM25",
                 "SULPHUR_DIOXIDE", "VOLATILE_ORGANIC_COMPOUNDS"):
        assert table[getattr(device_class_enum, name)] == MICROGRAMS, name


def test_loading_the_thermostat_logs_no_deprecation(caplog):
    with caplog.at_level(logging.WARNING):
        importlib.reload(climate_platform)
    assert _complaints(caplog) == []


def unit_of(entity):
    """The unit the thermostat reports, under whichever name this Home Assistant uses."""
    if hasattr(type(entity), "native_temperature_unit"):
        return entity.native_temperature_unit
    return entity.temperature_unit


def thermostat(**extra):
    entity = climate_platform.VirtualClimate(
        climate_platform.CLIMATE_SCHEMA({"name": "Hall", **extra}), False)
    entity._create_state(entity._config)
    return entity


def test_the_thermostat_uses_the_unit_name_this_home_assistant_understands():
    """Home Assistant only complains about the old name inside a running instance,
    so the log tests here cannot see it: check the choice itself. The new name is
    for a Home Assistant that has it, the old name for one that does not."""
    from homeassistant.components.climate import ClimateEntity
    expected = ("_attr_native_temperature_unit"
                if hasattr(ClimateEntity, "native_temperature_unit")
                else "_attr_temperature_unit")
    assert climate_platform._UNIT_ATTR == expected


def test_building_a_thermostat_logs_no_deprecation_a_test_can_see(caplog):
    # Only catches what Home Assistant logs inside a test (it does not log the old
    # unit name there); the name check above covers that.
    with caplog.at_level(logging.WARNING):
        thermostat(temperature_unit="°F")
        thermostat()
    assert _complaints(caplog) == []


def test_a_plain_thermostat_is_celsius_and_starts_at_21():
    entity = thermostat()
    assert unit_of(entity) == UnitOfTemperature.CELSIUS
    assert entity.target_temperature == 21.0


def test_a_fahrenheit_clone_is_fahrenheit_and_starts_at_70():
    """A Fahrenheit clone starting at 21 would sit outside its own limits."""
    # Wide limits: 21 and 70 are both inside them, so only the unit decides.
    entity = thermostat(temperature_unit="°F", min_temp=10, max_temp=120)
    assert unit_of(entity) == UnitOfTemperature.FAHRENHEIT
    assert entity.target_temperature == 70.0


def test_a_lowercase_fahrenheit_unit_is_still_fahrenheit():
    assert unit_of(thermostat(temperature_unit="°f")) == UnitOfTemperature.FAHRENHEIT


def test_a_start_outside_a_fahrenheit_clones_limits_moves_to_the_middle_of_them():
    """70 is outside 40-60, so the thermostat starts at the middle of its own range."""
    assert thermostat(temperature_unit="°F", min_temp=40, max_temp=60).target_temperature == 50.0


def test_a_start_outside_a_celsius_clones_limits_moves_to_the_middle_of_them():
    assert thermostat(temperature_unit="°C", min_temp=30, max_temp=40).target_temperature == 35.0


def test_a_celsius_clone_stays_celsius():
    entity = thermostat(temperature_unit="°C", min_temp=0, max_temp=100)
    assert unit_of(entity) == UnitOfTemperature.CELSIUS
    assert entity.target_temperature == 21.0


class Hass:
    """Records what is handed to the executor, so a test can tell disk work
    went off the event loop."""

    def __init__(self, yaml_config=False):
        self.executor_calls = []
        self.data = {cam.COMPONENT_CONFIG: {cam.CONF_YAML_CONFIG: yaml_config}}

    async def async_add_executor_job(self, func, *args):
        self.executor_calls.append(func)
        return func(*args)


def _entities_from_setup(monkeypatch, hass):
    monkeypatch.setattr(cam, "get_entity_configs",
                        lambda _h, _g, _d: [{"name": "A"}, {"name": "B"}])

    class Entry:
        data = {"group_name": "G"}

    added = []
    run(cam.async_setup_entry(hass, Entry(), added.extend))
    return added


def test_setup_lists_the_images_folder_off_the_event_loop_once(monkeypatch):
    hass = Hass()
    scans = []
    real = cam._frames
    monkeypatch.setattr(cam, "_frames", lambda: scans.append(1) or real())
    added = _entities_from_setup(monkeypatch, hass)
    assert len(added) == 2
    assert len(scans) == 1, "each camera scanned the folder itself"
    assert len(hass.executor_calls) == 1
    # The monkeypatched function is what was handed over, so this also proves
    # it was the folder listing and not something else.
    assert all(c is cam._frames for c in hass.executor_calls)


def test_every_camera_made_by_setup_gets_the_whole_list_of_frames(monkeypatch):
    added = _entities_from_setup(monkeypatch, Hass())
    everything = cam._frames()
    assert len(everything) > 1, "the bundled frames are missing, so this proves nothing"
    assert all(c._frames == everything for c in added)


def test_a_camera_keeps_its_own_copy_of_the_frames():
    frames = [Path("a.jpg"), Path("b.jpg")]
    one = cam.VirtualCamera(cam.CAMERA_SCHEMA({"name": "One"}), False, frames)
    two = cam.VirtualCamera(cam.CAMERA_SCHEMA({"name": "Two"}), False, frames)
    one._frames.pop()
    assert len(two._frames) == 2 and len(frames) == 2, "cameras share one list"


def test_an_empty_list_means_no_frames_not_look_in_the_folder(monkeypatch):
    def boom():
        raise AssertionError("the camera listed the folder itself")

    monkeypatch.setattr(cam, "_frames", boom)
    assert cam.VirtualCamera(cam.CAMERA_SCHEMA({"name": "C"}), False, [])._frames == []


def test_yaml_setup_lists_the_folder_off_the_event_loop_and_hands_it_over(monkeypatch):
    hass = Hass(yaml_config=True)
    added = []
    scans = []
    real = cam._frames
    monkeypatch.setattr(cam, "_frames", lambda: scans.append(1) or real())
    run(cam.async_setup_platform(hass, cam.CAMERA_SCHEMA({"name": "Y"}),
                                 lambda entities, *_: added.extend(entities)))
    assert len(added) == 1
    assert hass.executor_calls == [cam._frames], "the folder was listed on the event loop"
    assert len(scans) == 1, "the camera listed the folder again itself"
    assert added[0]._frames == real()


def test_yaml_setup_does_nothing_when_yaml_is_not_in_use():
    hass = Hass(yaml_config=False)
    added = []
    run(cam.async_setup_platform(hass, cam.CAMERA_SCHEMA({"name": "Y"}),
                                 lambda entities, *_: added.extend(entities)))
    assert added == [] and hass.executor_calls == []


def test_a_camera_given_its_frames_does_not_look_in_the_folder(monkeypatch, tmp_path):
    def boom():
        raise AssertionError("the camera listed the folder itself")

    monkeypatch.setattr(cam, "_frames", boom)
    frame = tmp_path / "x.jpg"
    entity = cam.VirtualCamera(cam.CAMERA_SCHEMA({"name": "C"}), False, [frame])
    assert entity._frames == [frame]


def test_a_camera_given_nothing_still_finds_the_bundled_frames():
    assert len(cam.VirtualCamera(cam.CAMERA_SCHEMA({"name": "C"}), False)._frames) > 0
