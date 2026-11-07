"""Failing loudly, and failing without taking everything else down.

REGRESSION GUARD for two bench failures on 2026-08-29.

ONE PLATFORM MUST NOT STRAND THE OTHERS. Unloading used to be a single batch, so
one platform failing failed the whole unload. A group being edited reloaded,
notify raised `Config entry was never loaded!`, and the entry was left half-down:
21 entities stuck in the registry as `restored`/`unavailable`, nothing short of a
full Home Assistant restart bringing them back. Every device-driven test on that
bench silently became meaningless, which looks exactly like a compiler bug.

A NO-OP MUST NOT REPORT SUCCESS. Removing a device that wasn't in the group
returned success and did nothing, so a bench stayed full of devices somebody
believed they had deleted.
"""

import asyncio
import pathlib

import pytest
from homeassistant.exceptions import ConfigEntryNotReady

from conftest import FakeEntry, FakeHass, load_devices, run

from custom_components.virtual import VIRTUAL_PLATFORMS, async_setup_entry, async_unload_entry
from custom_components.virtual import clone as clone_module
from custom_components.virtual.cfg import _save_user_data
from custom_components.virtual.const import COMPONENT_DOMAIN
from custom_components.virtual.pistoncore_manage import (
    _async_create_device,
    _async_remove_device,
    _mutate_and_reload,
    check_entries,
    free_device_name,
)

try:
    from homeassistant.exceptions import ServiceValidationError
except ImportError:  # pragma: no cover - HA always has this
    ServiceValidationError = Exception


GROUP = "Test Group"


def _loaded_bench(tmp_path):
    """A hass with one group loaded, the way a live entry leaves it."""
    hass = FakeHass(config_dir=tmp_path)
    entry = FakeEntry(tmp_path / "virtual.yaml", group_name=GROUP)
    hass.config_entries.entries = [entry]
    hass.data[COMPONENT_DOMAIN] = {GROUP: {"entities": {}, "devices": []}}
    return hass, entry


class FakeCall:
    def __init__(self, **data):
        self.data = data


# --- one platform must not strand the others ---------------------------------

def test_unload_survives_a_platform_that_was_never_loaded(tmp_path):
    """THE bug: notify raising must not keep the whole group down."""
    hass, entry = _loaded_bench(tmp_path)
    hass.config_entries.unload_raises = {"notify"}

    assert run(async_unload_entry(hass, entry)) is True, (
        "one platform failing reported the whole unload as failed — Home "
        "Assistant then leaves every entity stranded as `restored`"
    )
    assert GROUP not in hass.data[COMPONENT_DOMAIN], (
        "the group's data was left behind, so setting up again would stack on it"
    )


def test_every_other_platform_is_still_attempted(tmp_path):
    """A failure part-way must not abandon the platforms after it."""
    hass, entry = _loaded_bench(tmp_path)
    hass.config_entries.unload_raises = {"notify"}

    run(async_unload_entry(hass, entry))

    assert set(hass.config_entries.unloaded) == set(VIRTUAL_PLATFORMS), (
        "some platforms were never asked to unload: "
        f"{set(VIRTUAL_PLATFORMS) - set(hass.config_entries.unloaded)}"
    )


def test_unload_survives_a_platform_reporting_failure(tmp_path):
    """The quieter variant: a platform returns False rather than raising."""
    hass, entry = _loaded_bench(tmp_path)
    hass.config_entries.unload_returns_false = {"camera"}

    assert run(async_unload_entry(hass, entry)) is True
    assert GROUP not in hass.data[COMPONENT_DOMAIN]


def test_unloading_twice_does_not_explode(tmp_path):
    """Popping the group used to raise KeyError the second time round."""
    hass, entry = _loaded_bench(tmp_path)

    assert run(async_unload_entry(hass, entry)) is True
    assert run(async_unload_entry(hass, entry)) is True


# --- a no-op must not report success ------------------------------------------

def test_removing_an_unknown_device_is_refused(tmp_path):
    """Silent success is what let a bench stay polluted."""
    hass, entry = _loaded_bench(tmp_path)
    path = str(tmp_path / "virtual.yaml")
    run(_save_user_data(path, {"Keep Me": [{"platform": "switch", "name": "Keep Me"}]}))

    with pytest.raises(ServiceValidationError):
        run(_async_remove_device(hass, FakeCall(device_name="Never Existed")))


def test_a_refused_removal_does_not_touch_the_file(tmp_path):
    """Refusing must abort before the group's file is rewritten."""
    hass, entry = _loaded_bench(tmp_path)
    path = str(tmp_path / "virtual.yaml")
    devices = {"Keep Me": [{"platform": "switch", "name": "Keep Me"}]}
    run(_save_user_data(path, devices))
    before = open(path, encoding="utf-8").read()

    with pytest.raises(ServiceValidationError):
        run(_async_remove_device(hass, FakeCall(device_name="Never Existed")))

    assert open(path, encoding="utf-8").read() == before
    assert run(load_devices(path)) == devices


def test_removing_a_real_device_still_works(tmp_path):
    """The guard must not break the thing it guards."""
    hass, entry = _loaded_bench(tmp_path)
    path = str(tmp_path / "virtual.yaml")
    run(_save_user_data(path, {
        "Keep Me": [{"platform": "switch", "name": "Keep Me"}],
        "Drop Me": [{"platform": "switch", "name": "Drop Me"}],
    }))

    run(_async_remove_device(hass, FakeCall(device_name="Drop Me")))

    assert list(run(load_devices(path))) == ["Keep Me"]
    assert hass.config_entries.reloads == 1, "a real removal must still reload"


# --- an entry or a name that would do damage is refused before anything is written

def _thermostat(*_args):
    return "Thermo", [{"platform": "switch", "name": "Power"}]


def test_free_device_name_takes_the_next_free_number():
    assert free_device_name({}, "A") == "A"
    assert free_device_name({"A": []}, "A") == "A (2)"
    assert free_device_name({"A": [], "A (2)": []}, "A") == "A (3)"


def test_an_entry_a_platform_would_reject_is_refused_and_nothing_is_written(tmp_path):
    """One entry failing its platform's schema raises inside that platform's setup
    loop, so every entity of that type in the group vanishes at the next reload —
    and the call used to report success."""
    hass, entry = _loaded_bench(tmp_path)
    call = FakeCall(device_name="Bad", entities=[
        {"platform": "switch", "name": "Fine"},
        {"platform": "switch", "name": "Broken", "no_such_option": 1}])

    with pytest.raises(ServiceValidationError, match="Broken"):
        run(_async_create_device(hass, call))

    assert not (tmp_path / "virtual.yaml").exists()
    assert hass.config_entries.reloads == 0


def test_an_unknown_platform_is_refused(tmp_path):
    hass, _entry = _loaded_bench(tmp_path)
    with pytest.raises(ServiceValidationError, match="not a platform"):
        run(check_entries(hass, [{"platform": "sensors", "name": "Typo"}]))


def test_a_good_entry_is_accepted(tmp_path):
    hass, _entry = _loaded_bench(tmp_path)
    run(check_entries(hass, [{"platform": "switch", "name": "Fine"}]))  # the control


def test_creating_over_an_existing_device_name_is_refused_not_replaced(tmp_path):
    hass, _entry = _loaded_bench(tmp_path)
    run(_async_create_device(hass, FakeCall(
        device_name="Same", entities=[{"platform": "switch", "name": "First"}])))

    with pytest.raises(ServiceValidationError, match="already has a device"):
        run(_async_create_device(hass, FakeCall(
            device_name="Same", entities=[{"platform": "switch", "name": "Second"}])))

    assert run(load_devices(str(tmp_path / "virtual.yaml")))["Same"][0]["name"] == "First"


def test_cloning_the_same_device_twice_keeps_both(monkeypatch, tmp_path):
    """The second clone used to replace the first, because both took the default
    name, and the earlier one was gone without a word."""
    monkeypatch.setattr(clone_module, "build_clone_spec", _thermostat)
    hass, _entry = _loaded_bench(tmp_path)

    run(clone_module._async_clone_device(hass, FakeCall(device_id="x")))
    run(clone_module._async_clone_device(hass, FakeCall(device_id="x")))

    devices = run(load_devices(str(tmp_path / "virtual.yaml")))
    assert sorted(devices) == ["Test — Thermo", "Test — Thermo (2)"]
    # every entity is qualified with ITS device's name, whatever that turned out to be
    assert devices["Test — Thermo (2)"][0]["name"] == "Test — Thermo (2) Power"
    assert devices["Test — Thermo"][0]["name"] == "Test — Thermo Power"


def test_a_name_the_user_chose_is_never_replaced_or_renumbered(monkeypatch, tmp_path):
    monkeypatch.setattr(clone_module, "build_clone_spec", _thermostat)
    hass, _entry = _loaded_bench(tmp_path)
    run(clone_module._async_clone_device(hass, FakeCall(device_id="x", device_name="Mine")))

    with pytest.raises(ServiceValidationError, match="Mine"):
        run(clone_module._async_clone_device(hass, FakeCall(device_id="x", device_name="Mine")))

    assert list(run(load_devices(str(tmp_path / "virtual.yaml")))) == ["Mine"]


# --- setup, clone and groups: the other doors to the same guards ---------------


def test_a_damaged_identity_file_stops_the_group_loading(tmp_path):
    """The error has to reach Home Assistant as 'not ready', before any device is
    made or any registry row removed. Calling the loader alone proves neither."""
    hass = FakeHass(config_dir=tmp_path)
    meta = pathlib.Path(hass.config.path(".storage/virtual.meta.json"))
    meta.write_text("{broken")
    devices = tmp_path / "virtual.yaml"
    devices.write_text("devices:\n  A:\n    - {platform: switch, name: A}\n")

    with pytest.raises(ConfigEntryNotReady, match="damaged"):
        run(async_setup_entry(hass, FakeEntry(devices)))

    assert meta.read_text() == "{broken", "the damaged file was overwritten"
    assert GROUP not in hass.data.get(COMPONENT_DOMAIN, {})


def test_cloning_an_entry_the_platform_would_reject_is_refused(monkeypatch, tmp_path):
    """Bad-entry refusal was only proved through create_device; the clone path
    has its own call to the check."""
    monkeypatch.setattr(clone_module, "build_clone_spec", lambda *a: (
        "Thermo", [{"platform": "number", "name": "Level"}]))  # a number with no range
    hass, _entry = _loaded_bench(tmp_path)

    with pytest.raises(ServiceValidationError, match="would not load"):
        run(clone_module._async_clone_device(hass, FakeCall(device_id="x")))

    assert not (tmp_path / "virtual.yaml").exists()
    assert hass.config_entries.reloads == 0


def test_an_entry_with_no_name_is_still_accepted(tmp_path):
    """The loader names it from its device; only the schema cannot know that."""
    hass, _entry = _loaded_bench(tmp_path)
    run(check_entries(hass, [{"platform": "switch"}]))


def test_a_deliberately_emptied_file_still_takes_a_new_device(tmp_path):
    """`devices: {}` says 'no devices' on purpose, even while the group is running;
    only a file that is MISSING is refused."""
    hass, entry = _loaded_bench(tmp_path)
    hass.data[COMPONENT_DOMAIN][GROUP]["devices"] = [{"device_id": "Old"}]
    (tmp_path / "virtual.yaml").write_text("devices: {}\n")

    run(_mutate_and_reload(hass, entry, "create", lambda d: d.update({"New": []})))

    assert list(run(load_devices(str(tmp_path / "virtual.yaml")))) == ["New"]


def test_two_groups_reload_independently(tmp_path):
    """The lock, the waiting count and the dirty mark are all per group, so two
    groups changed at once each get their own reload and neither blocks the other."""
    hass = FakeHass(config_dir=tmp_path)
    first = FakeEntry(tmp_path / "a.yaml", group_name="A", entry_id="e-a")
    second = FakeEntry(tmp_path / "b.yaml", group_name="B", entry_id="e-b")

    async def go():
        await asyncio.gather(
            _mutate_and_reload(hass, first, "create", lambda d: d.update({"X": []})),
            _mutate_and_reload(hass, second, "create", lambda d: d.update({"Y": []})))

    run(go())
    assert hass.config_entries.reloads == 2
    assert list(run(load_devices(str(tmp_path / "a.yaml")))) == ["X"]
    assert list(run(load_devices(str(tmp_path / "b.yaml")))) == ["Y"]
