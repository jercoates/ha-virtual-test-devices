"""A lock shows the code it was last sent.

A test lock has no keypad, so an automation that reacts to "a code was used" could not
be tried. Home Assistant's own lock actions take a `code`; the virtual lock now
records it as `last_code`, and clears it when a lock or unlock arrives with none, so
the attribute always describes the most recent action.

What is deliberately NOT here: a code list, or any validation of the code (a virtual
lock accepts whatever it is sent). A code is typed by the caller and lands in the
state and so in Home Assistant's history, so it must be a made-up test code. A REAL
lock's codes are never copied by a clone or an export (see test_capability_capture).
"""

from conftest import run

from custom_components.virtual.lock import LOCK_SCHEMA, VirtualLock


class Units:
    temperature_unit = "°C"


class Config:
    units = Units()


class Hass:
    config = Config()


def lock(**extra):
    entity = VirtualLock(Hass(), LOCK_SCHEMA({"name": "Front", **extra}), False)
    entity._create_state(entity._config)
    entity._update_attributes()
    return entity


def last_code(entity):
    return entity.extra_state_attributes["last_code"]


def test_a_fresh_lock_has_been_sent_no_code():
    assert last_code(lock()) is None


def test_unlocking_with_a_code_records_it():
    entity = lock(initial_value="locked")
    run(entity.async_unlock(code="4821"))
    assert last_code(entity) == "4821"
    assert entity.is_locked is False, "the code did not stop it unlocking"


def test_locking_with_a_code_records_it():
    entity = lock(initial_value="unlocked")
    run(entity.async_lock(code="1111"))
    assert last_code(entity) == "1111"
    assert entity.is_locked is True


def test_an_action_with_no_code_clears_it():
    """Otherwise 'who used the code' would still show the LAST keypad entry after the
    lock was turned by hand, and an automation would be fooled by a stale value."""
    entity = lock()
    run(entity.async_unlock(code="4821"))
    run(entity.async_lock())
    assert last_code(entity) is None


def test_a_number_sent_as_the_code_is_kept_as_text():
    entity = lock()
    run(entity.async_unlock(code=4821))
    assert last_code(entity) == "4821"


def test_a_code_that_starts_with_zero_keeps_its_zero():
    entity = lock()
    run(entity.async_unlock(code="0042"))
    assert last_code(entity) == "0042"


def test_the_code_is_recorded_when_the_lock_takes_time_to_move():
    """A lock configured to take a while to lock still reports the code at once."""
    entity = lock(locking_time=5)
    entity._start_operation = lambda: None   # no real timer in a unit test
    run(entity.async_unlock(code="4821"))
    assert last_code(entity) == "4821"
    assert entity.is_unlocking is True


def test_opening_the_latch_with_a_code_records_it():
    entity = lock()
    run(entity.async_open(code="9999"))
    assert last_code(entity) == "9999"


# --- an automation must still be triggered -------------------------------------

def sequence(entity):
    return entity.extra_state_attributes["sequence"]


def test_every_use_changes_what_home_assistant_sees_even_the_same_code_twice():
    """A real keypad fires on every entry. Using the same code on a lock already in
    that state changes neither the state nor the code, so without a count that changes
    each time an automation waiting for it never runs."""
    entity = lock(initial_value="unlocked")
    seen = []
    for _ in range(3):
        run(entity.async_unlock(code="4821"))
        seen.append(dict(entity.extra_state_attributes))
    assert [s["sequence"] for s in seen] == [1, 2, 3]
    assert all(s["last_code"] == "4821" for s in seen)
    assert seen[0] != seen[1] != seen[2], "each use must be a different state to Home Assistant"


def test_an_action_with_no_code_still_counts():
    entity = lock()
    run(entity.async_lock())
    run(entity.async_unlock())
    assert sequence(entity) == 2


def test_a_fresh_lock_starts_the_count_at_zero():
    assert sequence(lock()) == 0


# --- through a REAL Home Assistant: what an automation actually sees ------------
#
# The tests above call the lock directly. These run a real Home Assistant core (its
# state machine, its event bus and its own lock service handlers, which is where the
# code_format check and the default-code option live), because "an automation still
# triggers" is a claim about what Home Assistant announces, not about a dict.

import asyncio
import tempfile

import pytest
from homeassistant.core import EVENT_STATE_CHANGED, CoreState, HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError


def _real(coro_factory):
    """Run `coro_factory(hass, make_lock, events)` against a real Home Assistant."""
    async def go():
        hass = HomeAssistant(tempfile.mkdtemp())
        hass.set_state(CoreState.running)
        events = []
        hass.bus.async_listen(EVENT_STATE_CHANGED, callback(lambda ev: events.append(ev.data)))

        def make_lock(**extra):
            entity = VirtualLock(hass, LOCK_SCHEMA({"name": "Front", **extra}), False)
            entity.hass = hass
            entity.entity_id = "lock.front"
            entity._no_platform_reported = True   # added by hand, not through a platform
            entity._create_state(entity._config)
            entity._update_attributes()
            entity.async_write_ha_state()
            return entity

        try:
            return await coro_factory(hass, make_lock, events)
        finally:
            await hass.async_stop(force=True)
    return run(go())


def test_home_assistant_announces_every_use_even_the_same_code_twice():
    """The owner's top priority: using a code must still trigger automations. Using
    the same code on a lock already unlocked changes neither its state nor its code,
    so only `sequence` makes Home Assistant announce it."""
    async def go(hass, make_lock, events):
        entity = make_lock(initial_value="unlocked")
        events.clear()
        for _ in range(3):
            await entity.async_handle_unlock_service(code="4821")
            entity.async_write_ha_state()
        return events

    events = _real(go)
    assert len(events) == 3, f"Home Assistant announced {len(events)} of 3 uses"
    assert [e["new_state"].attributes["sequence"] for e in events] == [1, 2, 3]
    assert {e["new_state"].state for e in events} == {"unlocked"}, "state never changed"


def test_without_the_count_the_same_code_twice_is_invisible(monkeypatch):
    """The control that proves the test above can fail: take the count away and Home
    Assistant, correctly, announces nothing for a repeat use."""
    monkeypatch.setattr(VirtualLock, "_remember_code",
                        lambda self, kwargs: setattr(self, "_last_code", kwargs.get("code")))

    async def go(hass, make_lock, events):
        entity = make_lock(initial_value="unlocked")
        entity._update_attributes()
        entity.async_write_ha_state()
        events.clear()
        for _ in range(2):
            await entity.async_handle_unlock_service(code="4821")
            entity._update_attributes()
            entity.async_write_ha_state()
        return events

    assert len(_real(go)) <= 1, "a repeat use should be invisible without the count"


def test_the_code_a_service_call_carries_reaches_last_code():
    async def go(hass, make_lock, events):
        entity = make_lock(initial_value="locked")
        await entity.async_handle_unlock_service(code="4821")
        entity.async_write_ha_state()
        return hass.states.get("lock.front")

    state = _real(go)
    assert state.state == "unlocked" and state.attributes["last_code"] == "4821"


def test_a_lock_with_a_code_format_refuses_a_wrong_code_and_counts_nothing():
    """Home Assistant checks the code against `code_format` before the lock sees it, so
    a refused attempt must not count as a use."""
    async def go(hass, make_lock, events):
        entity = make_lock(initial_value="locked", code_format=r"\d{4}")
        with pytest.raises(ServiceValidationError):
            await entity.async_handle_unlock_service(code="12")
        with pytest.raises(ServiceValidationError):
            await entity.async_handle_unlock_service()
        refused = entity.extra_state_attributes["sequence"]
        await entity.async_handle_unlock_service(code="4821")
        return refused, entity.extra_state_attributes["sequence"], entity.is_locked

    refused, accepted, locked = _real(go)
    assert refused == 0, "a refused attempt was counted"
    assert accepted == 1 and locked is False


def test_a_default_code_set_in_home_assistants_options_shows_as_the_code():
    """Home Assistant fills in a default code on actions that carry none. Documented
    (README), so pinned here: last_code then shows it."""
    async def go(hass, make_lock, events):
        entity = make_lock(initial_value="locked")
        entity._lock_option_default_code = "9999"
        await entity.async_handle_unlock_service()
        return entity.extra_state_attributes["last_code"]

    assert _real(go) == "9999"


def test_a_restart_starts_the_code_and_the_count_afresh():
    """A restored lock must not carry a code forward (privacy) and restarts the count."""
    entity = lock(initial_value="locked")
    run(entity.async_unlock(code="4821"))
    run(entity.async_unlock(code="4821"))
    entity._restore_state(State("lock.front", "unlocked", {"last_code": "4821", "sequence": 7}),
                          entity._config)
    entity._update_attributes()
    assert last_code(entity) is None
    assert sequence(entity) == 0


@pytest.mark.parametrize("sent", [0, "0", "00"])
def test_a_code_that_looks_like_nothing_is_still_a_code(sent):
    """`0` is a code. Dropping it because it is falsy would read as 'no code used'."""
    entity = lock()
    run(entity.async_unlock(code=sent))
    assert last_code(entity) == str(sent)
