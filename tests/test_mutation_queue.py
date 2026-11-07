"""The create/remove queue.

REGRESSION GUARD. Before this was fixed, create_device and remove_device did
read-modify-write on one yaml file and then reloaded the config entry. Called
concurrently, every caller loaded the file before ANY caller saved it, so all but
the last were silently erased — measured on a clean HA: six concurrent creates
produced ONE device and reported no error at all.

If either test here fails, that data loss is back.
"""

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError

from conftest import load_devices, run

from custom_components.virtual.pistoncore_manage import _mutate_and_reload


def _add(name):
    def mutate(devices):
        devices[name] = [{"platform": "switch", "name": name}]
    return mutate


def _drop(name):
    def mutate(devices):
        devices.pop(name, None)
    return mutate


def test_concurrent_creates_all_survive(hass, entry, device_file):
    """Ten at once must produce ten. This is the lost update."""
    names = [f"Device {i}" for i in range(10)]

    async def go():
        await asyncio.gather(*(
            _mutate_and_reload(hass, entry, f"created {n}", _add(n)) for n in names))
        return await load_devices(str(device_file))

    devices = run(go())
    missing = [n for n in names if n not in devices]
    assert not missing, f"silently lost: {missing}"
    assert len(devices) == len(names)


def test_concurrent_removes_all_applied(hass, entry, device_file):
    """Remove has the identical shape and had the identical bug."""
    names = [f"Device {i}" for i in range(10)]

    async def go():
        await asyncio.gather(*(
            _mutate_and_reload(hass, entry, "create", _add(n)) for n in names))
        await asyncio.gather(*(
            _mutate_and_reload(hass, entry, "remove", _drop(n)) for n in names[:6]))
        return await load_devices(str(device_file))

    devices = run(go())
    assert sorted(devices) == sorted(names[6:]), devices


def test_creates_do_not_clobber_existing_devices(hass, entry, device_file):
    """A burst must not eat devices that were already there."""
    async def go():
        await _mutate_and_reload(hass, entry, "seed", _add("Keep Me"))
        await asyncio.gather(*(
            _mutate_and_reload(hass, entry, "create", _add(f"New {i}")) for i in range(8)))
        return await load_devices(str(device_file))

    devices = run(go())
    assert "Keep Me" in devices, "a concurrent burst erased a pre-existing device"
    assert len(devices) == 9


def test_burst_costs_one_reload(hass, entry):
    """Reloading per call is what made the race window wide enough to hit.

    A burst should collapse to a single reload — whoever finds nobody else
    waiting does it.
    """
    async def go():
        await asyncio.gather(*(
            _mutate_and_reload(hass, entry, "create", _add(f"Device {i}"))
            for i in range(8)))

    run(go())
    assert hass.config_entries.reloads < 8, (
        f"{hass.config_entries.reloads} reloads for 8 creates — not coalescing")
    assert hass.config_entries.reloads >= 1, "never reloaded, so nothing would appear"


def test_single_change_still_reloads(hass, entry):
    """Coalescing must not swallow the ONLY reload — one change, one reload."""
    run(_mutate_and_reload(hass, entry, "create", _add("Solo")))
    assert hass.config_entries.reloads == 1


# --- a change must not be written over a file that could not be read -----------

@pytest.mark.parametrize("damage", [
    "",                          # blank: a copy still being written looks like this
    "devices: [unclosed\n  - {",  # a typo in a hand edit
    "- just\n- a list\n",        # not a mapping
])
def test_an_unreadable_file_is_never_written_over(hass, entry, device_file, damage):
    """Reading such a file gives 'no devices'. Adding one device on top of that and
    saving replaced every existing device with it, and reported success."""
    device_file.write_text(damage)

    with pytest.raises(HomeAssistantError):
        run(_mutate_and_reload(hass, entry, "create", _add("New")))

    assert device_file.read_text() == damage, "the unreadable file was overwritten"
    assert hass.config_entries.reloads == 0


def test_a_file_that_went_missing_from_a_running_group_is_not_recreated(
        hass, entry, device_file):
    """A mount that did not come up reads as a missing file. Writing a new one with
    a single device in it, then reloading, would remove every other device."""
    hass.data["virtual"] = {"Test Group": {"devices": [{"device_id": "Keep Me"}]}}

    with pytest.raises(HomeAssistantError):
        run(_mutate_and_reload(hass, entry, "create", _add("New")))

    assert not device_file.exists()


def test_a_brand_new_group_may_create_its_file(hass, entry, device_file):
    """The control for the two above: a missing file is fine when nothing runs."""
    run(_mutate_and_reload(hass, entry, "create", _add("First")))
    assert "First" in run(load_devices(str(device_file)))


def test_a_bare_file_keeps_its_devices_and_loses_its_version(hass, entry, device_file):
    """`devices:` is optional, and a file with only a `version:` marker must not
    have that marker saved back as though it were a device."""
    device_file.write_text("version: 1\n")
    run(_mutate_and_reload(hass, entry, "create", _add("First")))
    assert list(run(load_devices(str(device_file)))) == ["First"]


# --- reload bookkeeping ------------------------------------------------------

def test_a_failed_last_call_still_reloads_what_the_earlier_ones_wrote(
        hass, entry, device_file):
    """A wrote and saw someone else waiting, so it skipped the reload. If that
    other call then failed, nobody reloaded and A's device sat in the file, not
    live."""
    def boom(devices):
        raise HomeAssistantError("no such device")

    async def go():
        await asyncio.gather(
            _mutate_and_reload(hass, entry, "create", _add("A")),
            _mutate_and_reload(hass, entry, "remove", boom),
            return_exceptions=True)

    run(go())
    assert "A" in run(load_devices(str(device_file)))
    assert hass.config_entries.reloads == 1, "A was written but nothing reloaded"


def test_a_cancelled_waiter_does_not_stop_later_reloads(hass, entry):
    """The count of waiting callers went up before the try, so a call cancelled
    while it waited for the lock left it above zero for good, and no later call on
    that group ever reloaded."""
    async def go():
        lock = hass.data.setdefault("pistoncore_mutation_locks", {}).setdefault(
            entry.entry_id, asyncio.Lock())
        async with lock:                      # hold the lock so the waiter queues
            waiter = asyncio.ensure_future(
                _mutate_and_reload(hass, entry, "create", _add("Never")))
            await asyncio.sleep(0)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        await _mutate_and_reload(hass, entry, "create", _add("After"))

    run(go())
    assert hass.config_entries.reloads == 1, "later calls no longer reload"
