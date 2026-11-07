"""What the panel is allowed to learn.

The panel is an admin tool, but its commands are the only thing between the
frontend and a group's configuration, and a group's entity configs can carry lock
and alarm codes and text defaults. So the listing is deliberately small: a name,
whether the group is running.

Registration itself (once per Home Assistant, admin-only, surviving a reload) can
only be proved against a running Home Assistant and is driven there; see the
spike notes in FORK_NOTES.md.
"""

import types

from conftest import FakeHass, run

import custom_components.virtual as virtual
from custom_components.virtual import export, panel


def _entry(name, file_name, state="loaded", **extra):
    data = {"group_name": name, "file_name": file_name, **extra}
    return types.SimpleNamespace(
        data=data, state=types.SimpleNamespace(value=state))


def _hass_with(*entries):
    hass = FakeHass()
    hass.config_entries.entries = list(entries)
    return hass


def test_a_group_is_listed_by_name_and_state_only():
    hass = _hass_with(_entry("Test Devices", "/config/secret_place/virtual.yaml"))

    assert panel.groups_summary(hass) == [{"name": "Test Devices", "state": "loaded"}]
    assert "secret_place" not in repr(panel.groups_summary(hass))


def test_nothing_from_inside_a_group_reaches_the_listing():
    """The control for the one above: even if an entry carried codes or entity
    configs in its data, the listing has no way to pass them on."""
    hass = _hass_with(_entry("G", "virtual.yaml", entities={"lock": [{"code": "1234"}]},
                             token="abc"))

    text = repr(panel.groups_summary(hass))
    assert "1234" not in text and "abc" not in text and "entities" not in text


def test_a_group_that_is_not_running_says_so():
    hass = _hass_with(_entry("Broken", "virtual.yaml", state="setup_retry"))
    assert panel.groups_summary(hass)[0]["state"] == "setup_retry"


def test_no_groups_is_an_empty_list_not_an_error():
    assert panel.groups_summary(_hass_with()) == []


def test_a_group_with_no_file_name_does_not_break_the_listing():
    entry = _entry("Odd", None)
    assert panel.groups_summary(_hass_with(entry))[0]["name"] == "Odd"


# --- the lists the panel shows -------------------------------------------------



def _row(entity_id, device_id=None, platform="virtual", name=None, disabled_by=None):
    return types.SimpleNamespace(
        entity_id=entity_id, device_id=device_id, platform=platform, name=name,
        original_name=None, disabled_by=disabled_by, domain=entity_id.split(".")[0])


def _device(device_id, name, identifiers=(), disabled_by=None, manufacturer=None, model=None):
    return types.SimpleNamespace(
        id=device_id, name=name, name_by_user=None, identifiers=set(identifiers),
        disabled_by=disabled_by, manufacturer=manufacturer, model=model)


def _registries(monkeypatch, rows_by_entry=None, devices=(), rows_by_device=None):
    by_id = {d.id: d for d in devices}
    monkeypatch.setattr(panel.er, "async_get", lambda hass: object())
    monkeypatch.setattr(panel.dr, "async_get", lambda hass: types.SimpleNamespace(
        async_get=by_id.get, devices=by_id))
    monkeypatch.setattr(panel.er, "async_entries_for_config_entry",
                        lambda reg, entry_id: (rows_by_entry or {}).get(entry_id, []))
    monkeypatch.setattr(panel.er, "async_entries_for_device",
                        lambda reg, device_id: [r for r in (rows_by_device or {}).get(device_id, []) if not r.disabled_by])


def test_every_template_is_a_valid_device_and_every_platform_has_one():
    """The catalog is data anyone may edit, so a typo in it must show up here and
    not as a refused 'Create'. Every platform the add-on provides must be offered."""
    schemas = export.load_platform_schemas()
    templates = panel.read_templates()

    assert templates, "no templates"
    names = [t["name"] for t in templates]
    assert len(names) == len(set(names)), "two templates share a name"
    for template in templates:
        assert template["entities"], template["name"]
        for entity in template["entities"]:
            assert export._problem({**entity, "name": "x"}, schemas) is None, (
                template["name"], entity)
    offered = {e["platform"] for t in templates for e in t["entities"]}
    assert offered == set(export.PLATFORM_SCHEMA_NAMES), (
        "a platform has no template", set(export.PLATFORM_SCHEMA_NAMES) ^ offered)


def test_the_device_list_groups_entities_under_their_device(monkeypatch):
    hass = _hass_with(types.SimpleNamespace(
        entry_id="e1", data={"group_name": "Bench", "file_name": "v.yaml"}))
    plug = _device("d1", "Test — Plug", {("virtual", "Test — Plug")})
    _registries(monkeypatch, {"e1": [
        _row("switch.t_plug", "d1", name="Test — Plug Power"),
        _row("sensor.t_plug_w", "d1"),
        _row("sensor.alone"),                                    # no device at all
        _row("sensor.hidden", "d1", disabled_by="user"),          # disabled: not shown
    ]}, devices=[plug])

    result = panel.devices_summary(hass)

    by_name = {d["name"]: d for d in result}
    assert sorted(by_name) == ["Test — Plug", "sensor.alone"]
    assert by_name["Test — Plug"]["key"] == "Test — Plug"
    assert by_name["Test — Plug"]["group"] == "Bench"
    assert [e["entity_id"] for e in by_name["Test — Plug"]["entities"]] == [
        "switch.t_plug", "sensor.t_plug_w"]
    assert by_name["sensor.alone"]["key"] is None   # nothing to remove it by
    assert all(set(e) == {"entity_id", "domain", "name"}
               for d in result for e in d["entities"])


def test_the_clone_list_leaves_out_test_devices_and_what_cannot_be_copied(monkeypatch):
    real = _device("r1", "Hall Thermostat", {("ecobee", "1")}, manufacturer="ecobee", model="Smart")
    mine = _device("v1", "Test — Hall", {("virtual", "Test — Hall")})
    off = _device("x1", "Retired", {("zwave", "2")}, disabled_by="user")
    only_sensors_we_cannot_copy = _device("u1", "Updater", {("hue", "3")})
    from_hub = _device("h1", "Supervisor", {("hassio", "4")})
    _registries(monkeypatch, devices=[real, mine, off, only_sensors_we_cannot_copy, from_hub],
                rows_by_device={
                    "r1": [_row("climate.hall", "r1", "ecobee"), _row("sensor.hall_t", "r1", "ecobee")],
                    "v1": [_row("switch.t_hall", "v1", "virtual")],
                    "x1": [_row("switch.old", "x1", "zwave")],
                    "u1": [_row("update.firmware", "u1", "hue")],
                    "h1": [_row("sensor.cpu", "h1", "hassio")],
                })

    result = panel.clonable_summary(_hass_with())

    assert [d["name"] for d in result] == ["Hall Thermostat"]
    assert result[0] == {"device_id": "r1", "name": "Hall Thermostat", "kind": "ecobee Smart",
                         "domains": ["climate", "sensor"], "entities": 2}


def test_a_device_whose_only_copyable_entity_is_disabled_is_not_offered(monkeypatch):
    """Home Assistant's own helper leaves disabled entities out of a device's list
    unless asked, and the clone list relies on that."""
    device = _device("d9", "Quiet Lamp", {("hue", "9")})
    _registries(monkeypatch, devices=[device], rows_by_device={
        "d9": [_row("light.quiet", "d9", "hue", disabled_by="user")]})
    assert panel.clonable_summary(_hass_with()) == []


# --- the panel is optional, and can never stop the test devices loading ---------

def _setup(monkeypatch, config, register=None):
    """Run the integration's own setup with the panel registration replaced by a spy."""
    calls = []

    async def fake_register(hass):
        calls.append(1)
        if register:
            raise register

    monkeypatch.setattr(panel, "async_register_panel", fake_register)
    monkeypatch.setattr(export, "async_register_export_service", lambda hass: None)
    ok = run(virtual.async_setup(FakeHass(), config))
    return ok, calls


def test_the_panel_is_registered_by_default(monkeypatch):
    ok, calls = _setup(monkeypatch, {"virtual": {"export_only": True}})
    assert ok is True and calls == [1]


def test_the_panel_is_registered_when_asked_for(monkeypatch):
    assert _setup(monkeypatch, {"virtual": {"export_only": True, "panel": True}})[1] == [1]


def test_panel_false_leaves_the_sidebar_entry_out_and_nothing_else(monkeypatch):
    ok, calls = _setup(monkeypatch, {"virtual": {"export_only": True, "panel": False}})
    assert ok is True, "setup must still succeed"
    assert calls == [], "the panel was registered although it was switched off"


def test_a_panel_that_cannot_be_registered_does_not_stop_setup(monkeypatch):
    """A convenience must never stop the test devices loading."""
    ok, calls = _setup(monkeypatch, {"virtual": {"export_only": True}}, register=ValueError("path taken"))
    assert calls == [1]
    assert ok is True


def test_the_panel_option_is_read_from_the_config_schema():
    parsed = virtual.CONFIG_SCHEMA({"virtual": {}})
    assert parsed["virtual"]["panel"] is True
    assert virtual.CONFIG_SCHEMA({"virtual": {"panel": False}})["virtual"]["panel"] is False


def test_every_template_is_in_a_category_and_only_a_phone_offers_an_alert_choice():
    """The Create tab groups kinds by category. Only a kind that RECEIVES messages (a phone)
    asks push or text; a switch or a light never does."""
    templates = panel.read_templates()
    assert all(t.get("category") for t in templates), "a template has no category"
    receiving = [t for t in templates if t.get("receives")]
    assert [t["name"] for t in receiving] == ["Phone (location and notifications)"]
    assert any(e["platform"] == "notify" for e in receiving[0]["entities"]), "nothing to set push/text on"
    assert not [t["name"] for t in templates
                if t.get("receives") and any(e["platform"] in ("switch", "light") for e in t["entities"])]
