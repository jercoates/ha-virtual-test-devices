"""Bringing devices in from an export file.

The rules being guarded, in plain words:
  * a device that is IDENTICAL to one already in the group is offered once and never
    added twice (the current state does not make a device different);
  * a device that merely shares a name, or an entity id, is added WITH A NUMBER and
    nothing is ever replaced;
  * names are never stripped automatically: they are shown, and changed only where
    the person typed a new one;
  * a file that cannot be read, or an entry the platforms would reject, changes
    nothing.
"""

import json

import pytest
import yaml

from conftest import FakeEntry, FakeHass, load_devices, run

from custom_components.virtual import bring_in
from custom_components.virtual.bring_in import (
    BringInError, Index, apply_renames, async_apply, check_ids_unique, classify,
    fingerprint, get_upload, looks_personal, parse_export, preview, put_upload,
    summarise,
)
from custom_components.virtual.cfg import _save_user_data
from custom_components.virtual.const import COMPONENT_DOMAIN

GROUP = "Bench"


def light(entity_id="light.kitchen", name="Kitchen", **extra):
    return {"platform": "light", "name": name, "entity_id": entity_id, **extra}


def device(name, entities, key=None, **meta):
    return {"name": name, **meta, "entities": entities}


def export_text(devices, header="# Exported by Virtual Test Devices 0.16.0 from Home Assistant 2026.11.0"):
    return header + "\n" + yaml.safe_dump({"version": 1, "devices": devices})


def parsed(devices):
    return parse_export(export_text(devices))["devices"]


def bench(tmp_path, existing=None):
    """A hass with one running group whose file holds `existing`."""
    hass = FakeHass(config_dir=tmp_path)
    entry = FakeEntry(tmp_path / "bench.yaml", group_name=GROUP)
    hass.config_entries.entries = [entry]
    hass.data[COMPONENT_DOMAIN] = {GROUP: {"entities": {}, "devices": []}}
    if existing is not None:
        run(_save_user_data(str(entry.data["file_name"]), existing))
    return hass, entry


def upload(hass, devices):
    return put_upload(hass, {"source": "", "devices": parsed(devices)})


# ───────────────────────────────────────────────────────────── reading a file

def test_a_file_is_read_into_devices_with_their_names_and_ids():
    result = parse_export(export_text({"d1": device("Hall Light", [light("light.hall", "Hall")],
                                                      manufacturer="Acme", model="B1")}))
    block = result["devices"]["d1"]
    assert block["name"] == "Hall Light" and block["manufacturer"] == "Acme"
    assert [e["entity_id"] for e in block["entities"]] == ["light.hall"]
    assert result["source"].startswith("Exported by Virtual Test Devices")


def test_a_group_file_in_the_shorthand_form_is_read_too():
    result = parse_export(yaml.safe_dump({"Test — Lamp": [light("light.lamp", "Lamp")]}))
    assert list(result["devices"]) == ["Test — Lamp"]
    assert result["devices"]["Test — Lamp"]["name"] == "Test — Lamp"


@pytest.mark.parametrize("text", [
    "", "just words", "- a\n- b\n", "devices: 5", "devices: {}", "version: 1",
    "devices:\n  d1:\n    name: X\n    entities: []\n", "devices: [unclosed",
])
def test_a_file_that_is_not_an_export_is_refused_with_a_reason(text):
    with pytest.raises(BringInError):
        parse_export(text)


def test_a_file_cannot_make_the_reader_build_objects():
    """Otherwise this file reads as a perfectly good export: only the plain-yaml reader
    refuses the tag, so a reader that builds objects would let it through."""
    text = ("devices:\n  d1:\n    name: !!python/tuple [a, b]\n    entities:\n"
            "      - {platform: light, entity_id: light.a, name: x}\n")
    with pytest.raises(BringInError, match="not valid yaml"):
        parse_export(text)


def test_the_summary_has_names_kinds_and_ids_and_no_states():
    text = export_text({"p": device("Phone", [{"platform": "device_tracker", "name": "Phone",
                                                "entity_id": "device_tracker.phone",
                                                "initial_value": "SECRET PLACE"}])})
    summary = summarise(parse_export(text)["devices"])
    assert "SECRET PLACE" not in json.dumps(summary)
    assert summary[0]["entities"] == [{"entity_id": "device_tracker.phone",
                                       "platform": "device_tracker", "name": "Phone"}]


def test_things_that_may_carry_a_persons_name_are_marked_and_nothing_else_is():
    assert looks_personal(device("A", [{"platform": "person", "entity_id": "person.x"}]))
    assert looks_personal(device("A", [{"platform": "device_tracker", "entity_id": "device_tracker.x"}]))
    assert looks_personal(device("A", [{"platform": "notify", "entity_id": "notify.mobile_app_x"}]))
    assert not looks_personal(device("A", [{"platform": "notify", "entity_id": "notify.kitchen_speaker"}]))
    assert not looks_personal(device("Living Room", [light()]))


# ─────────────────────────────────────── the same device, or a different one

def test_the_same_device_with_a_different_state_is_the_same_device():
    one = parsed({"a": device("Kitchen Light", [light(initial_value="on", unique_id="u1")])})
    two = parsed({"b": device("Kitchen Light", [light(initial_value="off", unique_id="u2")])})
    plan = classify(Index({"a": one["a"]}), "b", two["b"])
    assert plan == {"status": "same", "same_as": "Kitchen Light"}


def test_the_same_device_under_another_key_is_still_the_same_device():
    one = parsed({"a": device("Kitchen Light", [light()])})
    assert classify(Index({"zzz": one["a"]}), "a", one["a"])["status"] == "same"


@pytest.mark.parametrize("what, other", [
    ("another ability", light(supported_color_modes=["hs"])),
    ("another entity id", light("light.kitchen_two")),
    ("another entity name", light(name="Kitchen Two")),
])
def test_a_device_that_differs_in_anything_but_state_is_a_different_device(what, other):
    base = parsed({"a": device("Kitchen Light", [light()])})["a"]
    different = parsed({"b": device("Kitchen Light", [other])})["b"]
    assert fingerprint(base["name"], {}, base["entities"]) != fingerprint(
        different["name"], {}, different["entities"]), what


def test_another_manufacturer_makes_a_different_device_but_another_firmware_does_not():
    base = parsed({"a": device("Plug", [light()], manufacturer="Acme", model="P1", sw_version="1")})["a"]
    firmware = parsed({"b": device("Plug", [light()], manufacturer="Acme", model="P1", sw_version="2")})["b"]
    maker = parsed({"c": device("Plug", [light()], manufacturer="Zed", model="P1")})["c"]
    index = Index({"a": base})
    assert classify(index, "b", firmware)["status"] == "same"
    assert classify(index, "c", maker)["status"] != "same"


def test_the_same_name_with_different_abilities_gets_a_number():
    here = parsed({"a": device("Kitchen Light", [light()])})
    there = parsed({"b": device("Kitchen Light", [light("light.other", supported_color_modes=["hs"])])})
    plan = classify(Index(here), "b", there["b"])
    assert plan["status"] == "renamed" and plan["name"] == "Kitchen Light (2)"
    assert plan["ids"] == {}


def test_numbers_keep_counting_and_never_reuse_one():
    taken = {"a": device("Lamp", [light("light.a")]), "b": device("Lamp (2)", [light("light.b")])}
    incoming = parsed({"c": device("Lamp", [light("light.c", supported_color_modes=["hs"])])})
    assert classify(Index(parsed(taken)), "c", incoming["c"])["name"] == "Lamp (3)"


def test_an_entity_id_already_in_use_gets_a_number_even_under_another_name():
    here = parsed({"a": device("Kitchen Light", [light()])})
    there = parsed({"b": device("Ceiling", [light("light.kitchen", "Ceiling")])})
    plan = classify(Index(here), "b", there["b"])
    assert plan["status"] == "renamed"
    assert plan["ids"] == {"light.kitchen": "light.kitchen_2"} and plan["name"] == "Ceiling"


def test_a_new_id_does_not_land_on_another_id_in_the_same_device():
    here = parsed({"a": device("X", [light("light.kitchen")])})
    there = parsed({"b": device("Y", [light("light.kitchen", "One"), light("light.kitchen_2", "Two")])})
    plan = classify(Index(here), "b", there["b"])
    assert plan["ids"] == {"light.kitchen": "light.kitchen_3"}


def test_the_preview_marks_a_copy_inside_the_file_itself():
    devices = parsed({"a": device("Lamp", [light("light.a")]), "b": device("Lamp", [light("light.a")])})
    status = preview(devices, Index({}))
    assert status["a"]["status"] == "new"
    assert status["b"] == {"status": "same", "same_as": "Lamp", "name": None, "ids": {}}


def test_the_preview_compares_with_what_the_groups_already_have():
    devices = parsed({"a": device("Lamp", [light("light.a")]), "b": device("Other", [light("light.a")])})
    status = preview(devices, Index({"x": devices["a"]}))
    assert status["a"]["status"] == "same"
    assert status["b"]["status"] == "renamed" and status["b"]["ids"] == {"light.a": "light.a_2"}


# ──────────────────────────────────────────────────────────── renaming names

def test_a_device_and_an_entity_can_be_renamed_and_the_original_is_not_touched():
    block = parsed({"d": device("Jane Smith's phone", [
        {"platform": "device_tracker", "name": "Jane Smith", "entity_id": "device_tracker.jane_smith"}])})["d"]
    new = apply_renames("d", block, {
        "devices": {"d": "Jane's phone"},
        "entities": {"device_tracker.jane_smith": {"name": "Jane", "entity_id": "device_tracker.jane"}}})
    assert new["name"] == "Jane's phone"
    assert new["entities"][0]["name"] == "Jane"
    assert new["entities"][0]["entity_id"] == "device_tracker.jane"
    assert block["name"] == "Jane Smith's phone"
    assert block["entities"][0]["entity_id"] == "device_tracker.jane_smith"


def test_blank_boxes_change_nothing():
    block = parsed({"d": device("Lamp", [light()])})["d"]
    assert apply_renames("d", block, {"devices": {"d": "  "},
                                      "entities": {"light.kitchen": {"name": "", "entity_id": ""}}}) == block


def test_a_new_id_made_by_renaming_does_not_keep_the_old_ids_unique_id():
    block = parsed({"d": device("Lamp", [light(unique_id="light.kitchen.virtual")])})["d"]
    new = apply_renames("d", block, {"entities": {"light.kitchen": {"entity_id": "light.den"}}})
    assert "unique_id" not in new["entities"][0]


def test_capitals_and_stray_spaces_in_a_new_id_are_tidied_not_refused():
    block = parsed({"d": device("Lamp", [light()])})["d"]
    new = apply_renames("d", block, {"entities": {"light.kitchen": {"entity_id": " Light.Den "}}})
    assert new["entities"][0]["entity_id"] == "light.den"


@pytest.mark.parametrize("bad", ["light.", "light den", "sensor.den", "den", "light.den.x", "light.d-n"])
def test_an_id_that_cannot_work_is_refused(bad):
    block = parsed({"d": device("Lamp", [light()])})["d"]
    with pytest.raises(BringInError):
        apply_renames("d", block, {"entities": {"light.kitchen": {"entity_id": bad}}})


def test_two_things_ending_up_with_the_same_id_is_refused():
    devices = parsed({"a": device("A", [light("light.a", "A")]), "b": device("B", [light("light.b", "B")])})
    renamed = {"a": devices["a"], "b": apply_renames(
        "b", devices["b"], {"entities": {"light.b": {"entity_id": "light.a"}}})}
    with pytest.raises(BringInError, match="light.a"):
        check_ids_unique(renamed)


# ────────────────────────────────────────────────────────────── held files

def test_a_held_file_can_be_fetched_and_an_unknown_one_cannot():
    hass = FakeHass()
    upload_id = put_upload(hass, {"source": "", "devices": {}})
    assert get_upload(hass, upload_id)["devices"] == {}
    with pytest.raises(BringInError):
        get_upload(hass, "nope")


def test_a_held_file_expires(monkeypatch):
    hass = FakeHass()
    now = [1000.0]
    monkeypatch.setattr(bring_in.time, "monotonic", lambda: now[0])
    upload_id = put_upload(hass, {"source": "", "devices": {}})
    now[0] += bring_in.UPLOAD_LIFETIME + 1
    with pytest.raises(BringInError):
        get_upload(hass, upload_id)


def test_only_a_few_files_are_held_and_the_oldest_goes_first(monkeypatch):
    hass = FakeHass()
    now = [0.0]
    monkeypatch.setattr(bring_in.time, "monotonic", lambda: now[0])
    ids = []
    for _ in range(bring_in.MAX_UPLOADS + 2):
        now[0] += 1
        ids.append(put_upload(hass, {"source": "", "devices": {}}))
    held = hass.data[bring_in._UPLOADS]
    assert len(held) == bring_in.MAX_UPLOADS
    assert ids[0] not in held and ids[-1] in held


# ─────────────────────────────────────────────────────── adding to a group

def test_chosen_devices_are_added_with_their_details_and_one_reload(tmp_path):
    hass, entry = bench(tmp_path, {})
    up = upload(hass, {
        "a": device("Hall Light", [light("light.hall", "Hall")], manufacturer="Acme", model="B1", area="Hall"),
        "b": device("Porch", [light("light.porch", "Porch")]),
        "c": device("Not chosen", [light("light.nope", "Nope")])})
    result = run(async_apply(hass, up, GROUP, None, ["a", "b"], {}))
    assert result["added"] == ["Hall Light", "Porch"] and result["same"] == []
    saved = run(load_devices(entry.data["file_name"]))
    assert sorted(saved) == ["a", "b"]
    assert saved["a"]["manufacturer"] == "Acme" and saved["a"]["area"] == "Hall"
    assert saved["a"]["entities"][0]["entity_id"] == "light.hall"
    assert hass.config_entries.reloads == 1


def test_an_identical_device_is_not_added_a_second_time(tmp_path):
    hass, entry = bench(tmp_path, {})
    first = upload(hass, {"a": device("Lamp", [light("light.a", initial_value="on")])})
    run(async_apply(hass, first, GROUP, None, ["a"], {}))
    second = upload(hass, {"z": device("Lamp", [light("light.a", initial_value="off")]),
                           "y": device("Fan", [{"platform": "fan", "name": "Fan", "entity_id": "fan.f"}])})
    result = run(async_apply(hass, second, GROUP, None, ["z", "y"], {}))
    assert result["added"] == ["Fan"]
    assert result["same"] == [{"name": "Lamp", "same_as": "Lamp"}]
    assert sorted(run(load_devices(entry.data["file_name"]))) == ["a", "y"]


def test_when_everything_chosen_is_already_there_nothing_is_written(tmp_path):
    hass, entry = bench(tmp_path, {})
    up = upload(hass, {"a": device("Lamp", [light("light.a")])})
    run(async_apply(hass, up, GROUP, None, ["a"], {}))
    reloads, before = hass.config_entries.reloads, open(entry.data["file_name"]).read()
    again = upload(hass, {"q": device("Lamp", [light("light.a")])})
    with pytest.raises(BringInError, match="already here"):
        run(async_apply(hass, again, GROUP, None, ["q"], {}))
    assert open(entry.data["file_name"]).read() == before
    assert hass.config_entries.reloads == reloads


def test_two_peoples_files_mix_and_clashes_get_numbers(tmp_path):
    hass, entry = bench(tmp_path, {})
    alice = upload(hass, {"a": device("Kitchen Light", [light("light.kitchen")]),
                          "b": device("Hall Fan", [{"platform": "fan", "name": "Fan", "entity_id": "fan.hall"}])})
    bob = upload(hass, {"c": device("Kitchen Light", [light("light.kitchen", supported_color_modes=["hs"])]),
                        "d": device("Hall Fan", [{"platform": "fan", "name": "Fan", "entity_id": "fan.hall"}])})
    run(async_apply(hass, alice, GROUP, None, ["a", "b"], {}))
    result = run(async_apply(hass, bob, GROUP, None, ["c", "d"], {}))
    assert result["added"] == ["Kitchen Light (2)"]
    assert result["renamed"] == [{"was": "Kitchen Light", "now": "Kitchen Light (2)",
                                  "ids": {"light.kitchen": "light.kitchen_2"}}]
    assert result["same"] == [{"name": "Hall Fan", "same_as": "Hall Fan"}]
    saved = run(load_devices(entry.data["file_name"]))
    ids = sorted(e["entity_id"] for block in saved.values() for e in block["entities"])
    assert ids == ["fan.hall", "light.kitchen", "light.kitchen_2"]
    assert len(ids) == len(set(ids))


def test_two_identical_devices_ticked_together_are_added_once(tmp_path):
    hass, entry = bench(tmp_path, {})
    up = upload(hass, {"a": device("Lamp", [light("light.a")]), "b": device("Lamp", [light("light.a")])})
    result = run(async_apply(hass, up, GROUP, None, ["a", "b"], {}))
    assert result["added"] == ["Lamp"] and len(result["same"]) == 1


def test_typed_names_are_what_gets_saved_and_the_old_ones_are_not_in_the_file(tmp_path):
    hass, entry = bench(tmp_path, {})
    up = upload(hass, {"p": device("Jane Smith's phone", [
        {"platform": "device_tracker", "name": "Jane Smith", "entity_id": "device_tracker.jane_smith"}])})
    run(async_apply(hass, up, GROUP, None, ["p"], {
        "devices": {"p": "Jane's phone"},
        "entities": {"device_tracker.jane_smith": {"name": "Jane", "entity_id": "device_tracker.jane"}}}))
    text = open(entry.data["file_name"]).read()
    assert "Jane's phone" in text and "entity_id: device_tracker.jane" in text
    assert "Smith" not in text and "jane_smith" not in text


def test_an_entry_the_platforms_would_reject_changes_nothing(tmp_path):
    hass, entry = bench(tmp_path, {"keep": [light("light.keep", "Keep")]})
    before = open(entry.data["file_name"]).read()
    up = upload(hass, {"bad": device("Bad", [light("light.bad", bogus_option=1)])})
    with pytest.raises(Exception, match="would not load"):
        run(async_apply(hass, up, GROUP, None, ["bad"], {}))
    assert open(entry.data["file_name"]).read() == before and hass.config_entries.reloads == 0


def test_nothing_ticked_or_a_device_not_in_the_file_changes_nothing(tmp_path):
    hass, entry = bench(tmp_path, {})
    up = upload(hass, {"a": device("Lamp", [light()])})
    with pytest.raises(BringInError, match="ticked"):
        run(async_apply(hass, up, GROUP, None, [], {}))
    with pytest.raises(BringInError, match="not in that file"):
        run(async_apply(hass, up, GROUP, None, ["ghost"], {}))
    assert hass.config_entries.reloads == 0


def test_a_group_file_that_cannot_be_read_is_not_written_over(tmp_path):
    hass, entry = bench(tmp_path)
    open(entry.data["file_name"], "w").write("devices: [broken")
    up = upload(hass, {"a": device("Lamp", [light()])})
    with pytest.raises(Exception, match="could not be read"):
        run(async_apply(hass, up, GROUP, None, ["a"], {}))
    assert open(entry.data["file_name"]).read() == "devices: [broken"


def test_a_new_group_is_made_for_the_devices_when_one_is_named(tmp_path, monkeypatch):
    hass, _entry = bench(tmp_path, {})
    made = []

    async def fake_create(hass_, name):
        made.append(name)
        entry = FakeEntry(tmp_path / "virtual_sams_house.yaml", group_name=name, entry_id="entry-2")
        hass_.config_entries.entries.append(entry)

    monkeypatch.setattr(bring_in, "_create_group", fake_create)
    up = upload(hass, {"a": device("Lamp", [light()])})
    result = run(async_apply(hass, up, None, "Sam's house", ["a"], {}))
    assert made == ["Sam's house"] and result["group"] == "Sam's house"
    assert sorted(run(load_devices(str(tmp_path / "virtual_sams_house.yaml")))) == ["a"]


def test_a_bad_entry_does_not_leave_a_new_group_behind(tmp_path, monkeypatch):
    hass, _entry = bench(tmp_path, {})
    made = []

    async def fake_create(hass_, name):
        made.append(name)

    monkeypatch.setattr(bring_in, "_create_group", fake_create)
    up = upload(hass, {"bad": device("Bad", [light("light.bad", bogus_option=1)])})
    with pytest.raises(Exception):
        run(async_apply(hass, up, None, "Sam", ["bad"], {}))
    assert made == [], "the group was made before the entries were checked"


# ───────────────────────────────────────────────────────── the upload endpoint

class Body:
    def __init__(self, data, user, hass=None):
        self._data, self.user = data, user
        self.app = {bring_in.KEY_HASS: hass or FakeHass(config_dir=None)}

    def get(self, key, default=None):
        return self.user if key == bring_in.KEY_HASS_USER else default

    async def read(self):
        return self._data


class User:
    def __init__(self, is_admin):
        self.is_admin = is_admin


def post(data, admin=True, hass=None):
    request = Body(data, User(admin), hass)
    reply = run(bring_in.ImportUploadView().post(request))
    return reply, request.app[bring_in.KEY_HASS]


def test_only_an_administrator_can_send_a_file():
    reply, hass = post(export_text({"a": device("Lamp", [light()])}).encode(), admin=False)
    assert reply.status == 403 and bring_in._UPLOADS not in hass.data


def test_an_uploaded_file_comes_back_as_a_list_and_is_held():
    reply, hass = post(export_text({"a": device("Lamp", [light()])}).encode())
    body = json.loads(reply.text)
    assert reply.status == 200 and body["devices"][0]["name"] == "Lamp"
    assert get_upload(hass, body["upload_id"])["devices"]["a"]["name"] == "Lamp"


@pytest.mark.parametrize("data, status", [
    (b"\xff\xfe not text", 400), (b"hello", 400),
    (b"x" * (bring_in.UPLOAD_LIMIT + 1), 413),
])
def test_a_file_that_is_not_an_export_gets_a_plain_error(data, status):
    reply, hass = post(data)
    assert reply.status == status and json.loads(reply.text)["message"]
    assert bring_in._UPLOADS not in hass.data


# ───────────────────────────────────────── ids belong to every group, not one

def two_groups(tmp_path, first, second):
    hass = FakeHass(config_dir=tmp_path)
    one = FakeEntry(tmp_path / "one.yaml", group_name="One", entry_id="e1")
    two = FakeEntry(tmp_path / "two.yaml", group_name="Two", entry_id="e2")
    hass.config_entries.entries = [one, two]
    hass.data[COMPONENT_DOMAIN] = {"One": {"entities": {}, "devices": []},
                                   "Two": {"entities": {}, "devices": []}}
    run(_save_user_data(str(one.data["file_name"]), first))
    run(_save_user_data(str(two.data["file_name"]), second))
    return hass, one, two


def test_the_same_id_in_another_group_gets_a_number(tmp_path):
    here = parsed({"a": device("Kitchen Light", [light()])})
    hass, one, two = two_groups(tmp_path, here, {})
    up = upload(hass, {"c": device("Ceiling", [light("light.kitchen", "Ceiling")])})
    result = run(async_apply(hass, up, "Two", None, ["c"], {}))
    assert result["renamed"][0]["ids"] == {"light.kitchen": "light.kitchen_2"}
    ids = [e["entity_id"] for g in (one, two) for b in run(load_devices(g.data["file_name"])).values()
           for e in b["entities"]]
    assert sorted(ids) == ["light.kitchen", "light.kitchen_2"]


def test_a_device_identical_to_one_in_another_group_is_not_added(tmp_path):
    here = parsed({"a": device("Kitchen Light", [light()])})
    hass, one, two = two_groups(tmp_path, here, {})
    up = upload(hass, {"z": device("Kitchen Light", [light(initial_value="off")])})
    with pytest.raises(BringInError, match="already here"):
        run(async_apply(hass, up, "Two", None, ["z"], {}))
    assert run(load_devices(two.data["file_name"])) == {}


def test_the_preview_looks_at_every_group_at_once():
    first = parsed({"a": device("Lamp", [light("light.a", "A")])})
    second = parsed({"b": device("Fan", [{"platform": "fan", "name": "Fan", "entity_id": "fan.f"}])})
    incoming = parsed({"x": device("Lamp", [light("light.a", "A")]),
                       "y": device("Other fan", [{"platform": "fan", "name": "Fan", "entity_id": "fan.f"}])})
    status = preview(incoming, Index(first, second))
    assert status["x"]["status"] == "same" and status["y"]["ids"] == {"fan.f": "fan.f_2"}


def test_a_group_whose_file_cannot_be_read_stops_the_comparison(tmp_path):
    hass, one, two = two_groups(tmp_path, {}, {})
    open(two.data["file_name"], "w").write("devices: [broken")
    up = upload(hass, {"a": device("Lamp", [light()])})
    with pytest.raises(BringInError, match="'Two'"):
        run(async_apply(hass, up, "One", None, ["a"], {}))
    assert run(load_devices(one.data["file_name"])) == {}


# ───────────────────────────────────────────── found by the review: hostile and racing

def test_a_tiny_file_that_stands_for_a_gigantic_one_is_refused_quickly():
    """yaml aliases: nine references to the level below, ten levels deep, is under 2 KB of
    text and about 10**9 values. Without a limit the reader spins and eats the machine."""
    import threading
    lines = ["l0: &l0 [x, x, x, x, x, x, x, x, x]"]
    for level in range(1, 10):
        lines.append(f"l{level}: &l{level} [" + ", ".join([f"*l{level - 1}"] * 9) + "]")
    text = "\n".join(lines) + "\ndevices:\n  d:\n    name: *l9\n    entities:\n      - {platform: light, entity_id: light.a}\n"
    outcome = []

    def attempt():
        try:
            parse_export(text)
            outcome.append("read it")
        except BringInError as err:
            outcome.append(str(err))

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(30)
    assert not worker.is_alive(), "the reader is still busy: nothing limits what a file expands to"
    assert "stands for far more" in outcome[0]


def test_a_list_shared_between_two_entities_is_still_a_good_export():
    """Home Assistant's own writer emits yaml aliases when one list is used twice, so
    refusing every alias would refuse real exports."""
    from homeassistant.util.yaml import dump
    shared = ["hs", "rgb"]
    text = dump({"devices": {"d": {"name": "Lamps", "entities": [
        {"platform": "light", "entity_id": "light.a", "name": "A", "supported_color_modes": shared},
        {"platform": "light", "entity_id": "light.b", "name": "B", "supported_color_modes": shared}]}}})
    assert "&id001" in text and "*id001" in text, "the writer no longer shares it, so this proves nothing"
    assert [e["entity_id"] for e in parse_export(text)["devices"]["d"]["entities"]] == ["light.a", "light.b"]


def test_entity_ids_are_compared_in_lower_case_and_one_that_is_not_text_is_ignored():
    result = parse_export(yaml.safe_dump({"devices": {"d": {"name": "X", "entities": [
        {"platform": "light", "entity_id": " Light.Foo ", "name": "A"},
        {"platform": "light", "entity_id": ["light", "bar"], "name": "B"}]}}}))
    ids = [e.get("entity_id") for e in result["devices"]["d"]["entities"]]
    assert ids == ["light.foo", None]
    index = Index({"x": parsed({"x": device("Foo", [light("light.foo", "Foo")])})["x"]})
    assert classify(index, "d", result["devices"]["d"])["ids"] == {"light.foo": "light.foo_2"}


def test_two_imports_at_the_same_moment_into_different_groups_do_not_share_an_id(tmp_path, monkeypatch):
    import asyncio
    hass = FakeHass(config_dir=tmp_path)
    hass.config_entries.entries = []
    hass.data[COMPONENT_DOMAIN] = {}

    async def fake_create(hass_, name):
        entry = FakeEntry(tmp_path / f"{name}.yaml", group_name=name, entry_id=f"e-{name}")
        hass_.config_entries.entries.append(entry)
        await asyncio.sleep(0)

    monkeypatch.setattr(bring_in, "_create_group", fake_create)
    one = upload(hass, {"a": device("Porch", [light("light.race", "Race")])})
    two = upload(hass, {"b": device("Garden", [light("light.race", "Race", supported_color_modes=["hs"])])})

    async def both():
        return await asyncio.gather(async_apply(hass, one, None, "RaceA", ["a"], {}),
                                    async_apply(hass, two, None, "RaceB", ["b"], {}))

    run(both())
    ids = [e["entity_id"] for name in ("RaceA", "RaceB")
           for block in run(load_devices(str(tmp_path / f"{name}.yaml"))).values()
           for e in block["entities"]]
    assert sorted(ids) == ["light.race", "light.race_2"], ids


def test_nothing_is_made_when_everything_ticked_is_already_here(tmp_path, monkeypatch):
    hass, _entry = bench(tmp_path, {})
    made = []

    async def fake_create(hass_, name):
        made.append(name)

    monkeypatch.setattr(bring_in, "_create_group", fake_create)
    first = upload(hass, {"a": device("Lamp", [light("light.a")])})
    run(async_apply(hass, first, GROUP, None, ["a"], {}))
    again = upload(hass, {"z": device("Lamp", [light("light.a")])})
    with pytest.raises(BringInError, match="already here"):
        run(async_apply(hass, again, None, "Empty one", ["z"], {}))
    assert made == [], "a group was made for devices that were not added"


def test_nothing_comes_in_on_a_home_assistant_set_to_export_only(tmp_path):
    from custom_components.virtual.const import COMPONENT_CONFIG, CONF_EXPORT_ONLY
    hass, entry = bench(tmp_path, {})
    hass.data[COMPONENT_CONFIG] = {CONF_EXPORT_ONLY: True}
    up = upload(hass, {"a": device("Lamp", [light()])})
    with pytest.raises(BringInError, match="export only"):
        run(async_apply(hass, up, GROUP, None, ["a"], {}))
    assert run(load_devices(entry.data["file_name"])) == {}
    reply, _ = post(export_text({"a": device("Lamp", [light()])}).encode(), hass=hass)
    assert reply.status == 400 and "export only" in json.loads(reply.text)["message"]


def test_a_device_that_is_one_entity_is_not_filed_under_the_old_id_after_a_rename(tmp_path):
    hass, entry = bench(tmp_path, {})
    up = upload(hass, {"person.jane_smith": device("Jane Smith", [
        {"platform": "device_tracker", "name": "Jane Smith", "entity_id": "person.jane_smith"}])})
    # (a person is not a device_tracker, but the key rule is the same for any lone entity)
    run(async_apply(hass, up, GROUP, None, ["person.jane_smith"], {
        "entities": {"person.jane_smith": {"entity_id": "device_tracker.jj"}}}))
    saved = open(entry.data["file_name"]).read()
    assert "person.jane_smith" not in saved, saved
    assert list(run(load_devices(entry.data["file_name"]))) == ["device_tracker.jj"]


def test_typed_names_of_the_wrong_shape_are_refused_with_a_reason_not_a_crash():
    for bad in ({"devices": ["x"]}, {"entities": {"a": "b"}}, {"entities": ["a"]}, {"devices": {"a": 5}}):
        with pytest.raises(Exception) as caught:
            bring_in.RENAMES_SCHEMA(bad)
        assert any("Invalid" in cls.__name__ for cls in type(caught.value).__mro__), bad
    assert bring_in.RENAMES_SCHEMA({}) == {"devices": {}, "entities": {}}


def test_the_apply_command_itself_refuses_typed_names_of_the_wrong_shape():
    """Home Assistant checks a command's arguments before its handler runs, so a wrong shape
    must be refused here and never reach the code that would crash on it."""
    schema = bring_in._ws_apply._ws_schema
    good = {"id": 1, "type": bring_in.WS_APPLY, "upload_id": "u", "group": "G", "keys": ["a"]}
    assert schema(good)["renames"] == {"devices": {}, "entities": {}}
    for bad in (["x"], {"entities": {"a": "b"}}, {"devices": {"a": 5}}):
        with pytest.raises(Exception) as caught:
            schema({**good, "renames": bad})
        assert any("Invalid" in cls.__name__ for cls in type(caught.value).__mro__), bad


# ───────────────────────────────── the commands the panel talks to (found by the review)

class Connection:
    """Just enough of a websocket connection: who is asking, and what was answered."""

    def __init__(self, admin=True):
        self.user = User(admin)
        self.results, self.errors = [], []
        self.refused = False

    def send_result(self, msg_id, result=None):
        self.results.append((msg_id, result))

    def send_error(self, msg_id, code, message):
        self.errors.append((msg_id, code, message))


class WsHass(FakeHass):
    """A hass that runs the background task a command is wrapped in."""

    def __init__(self, config_dir=None):
        super().__init__(config_dir=config_dir)
        self.tasks = []

    def async_create_background_task(self, coro, *args, **kwargs):
        self.tasks.append(coro)


def command(handler, hass, msg, admin=True):
    """Run a command the way Home Assistant does: arguments checked (and defaults filled in)
    first, a non-administrator refused before the handler's own code."""
    from homeassistant.exceptions import Unauthorized
    connection = Connection(admin)
    try:
        handler(hass, connection, handler._ws_schema({"id": 7, **msg}))
    except Unauthorized:
        connection.refused = True
    for task in hass.tasks:
        run(task)
    hass.tasks.clear()
    return connection


def ws_bench(tmp_path, existing=None):
    hass = WsHass(config_dir=tmp_path)
    entry = FakeEntry(tmp_path / "bench.yaml", group_name=GROUP)
    hass.config_entries.entries = [entry]
    hass.data[COMPONENT_DOMAIN] = {GROUP: {"entities": {}, "devices": []}}
    if existing is not None:
        run(_save_user_data(str(entry.data["file_name"]), existing))
    return hass, entry


def test_apply_through_the_command_saves_the_names_that_were_typed(tmp_path):
    """The panel only sends what was typed; this is the path it takes to the file."""
    hass, entry = ws_bench(tmp_path, {})
    up = upload(hass, {"p": device("Jane Smith's phone", [
        {"platform": "device_tracker", "name": "Jane Smith", "entity_id": "device_tracker.jane_smith"}])})
    conn = command(bring_in._ws_apply, hass, {
        "type": bring_in.WS_APPLY, "upload_id": up, "group": GROUP, "keys": ["p"],
        "renames": {"devices": {"p": "Jane's phone"},
                    "entities": {"device_tracker.jane_smith": {"name": "Jane", "entity_id": "device_tracker.jane"}}}})
    assert conn.errors == [] and conn.results[0][1]["added"] == ["Jane's phone"]
    text = open(entry.data["file_name"]).read()
    assert "Jane's phone" in text and "Smith" not in text and "jane_smith" not in text


def test_apply_through_the_command_uses_the_group_chosen_and_strips_a_new_groups_name(tmp_path, monkeypatch):
    hass, entry = ws_bench(tmp_path, {})
    made = []

    async def fake_create(hass_, name):
        made.append(name)
        hass_.config_entries.entries.append(FakeEntry(tmp_path / "new.yaml", group_name=name, entry_id="e2"))

    monkeypatch.setattr(bring_in, "_create_group", fake_create)
    up = upload(hass, {"a": device("Lamp", [light()])})
    conn = command(bring_in._ws_apply, hass, {"type": bring_in.WS_APPLY, "upload_id": up,
                                              "new_group": "  Sam's house ", "keys": ["a"]})
    assert made == ["Sam's house"] and conn.results[0][1]["group"] == "Sam's house"
    assert run(load_devices(entry.data["file_name"])) == {}, "it went to the new group, not the old one"


def test_apply_through_the_command_needs_a_group_or_a_new_name(tmp_path):
    hass, _ = ws_bench(tmp_path, {})
    up = upload(hass, {"a": device("Lamp", [light()])})
    conn = command(bring_in._ws_apply, hass, {"type": bring_in.WS_APPLY, "upload_id": up, "keys": ["a"]})
    assert conn.results == [] and "Choose a group" in conn.errors[0][2]


def test_a_problem_with_an_import_is_answered_in_words_not_as_a_crash(tmp_path):
    hass, _ = ws_bench(tmp_path, {})
    up = upload(hass, {"a": device("Lamp", [light()])})
    conn = command(bring_in._ws_apply, hass, {"type": bring_in.WS_APPLY, "upload_id": up,
                                              "group": GROUP, "keys": []})
    assert conn.errors == [(7, "virtual_bring_in", "No devices are ticked.")]
    conn = command(bring_in._ws_apply, hass, {"type": bring_in.WS_APPLY, "upload_id": up,
                                              "group": "Nowhere", "keys": ["a"]})
    assert conn.errors[0][1] == "virtual_bring_in" and "Nowhere" in conn.errors[0][2]


def test_the_preview_command_compares_with_every_group(tmp_path):
    here = parsed({"a": device("Lamp", [light("light.a", "A")])})
    hass, _ = ws_bench(tmp_path, here)
    up = upload(hass, {"x": device("Lamp", [light("light.a", "A")]),
                       "y": device("Fan", [{"platform": "fan", "name": "Fan", "entity_id": "fan.f"}])})
    conn = command(bring_in._ws_preview, hass, {"type": bring_in.WS_PREVIEW, "upload_id": up})
    status = conn.results[0][1]["status"]
    assert status["x"]["status"] == "same" and status["y"]["status"] == "new"
    gone = command(bring_in._ws_preview, hass, {"type": bring_in.WS_PREVIEW, "upload_id": "nope"})
    assert "no longer held" in gone.errors[0][2]


def test_the_forget_command_lets_go_of_the_file(tmp_path):
    hass, _ = ws_bench(tmp_path, {})
    up = upload(hass, {"a": device("Lamp", [light()])})
    conn = command(bring_in._ws_forget, hass, {"type": bring_in.WS_FORGET, "upload_id": up})
    assert conn.results == [(7, {})]
    with pytest.raises(BringInError):
        get_upload(hass, up)


def test_the_export_review_command_shows_the_names_the_export_will_contain(tmp_path, monkeypatch):
    from custom_components.virtual import export
    hass, _ = ws_bench(tmp_path, {})
    seen = {}

    def fake_collect(hass_, data, schemas):
        seen.update(data)
        return ({"d1": {"name": "Jane's phone", "manufacturer": "Apple", "entities": [
            {"platform": "device_tracker", "name": "Jane", "entity_id": "device_tracker.jane",
             "initial_value": "SECRET PLACE"}]}}, [])

    monkeypatch.setattr(export, "_collect", fake_collect)
    monkeypatch.setattr(export, "load_platform_schemas", lambda: {})
    conn = command(bring_in._ws_export_review, hass, {
        "type": bring_in.WS_EXPORT_REVIEW, "exclude_entities": ["sensor.*"], "exclude_devices": ["Hall*"]})
    assert conn.errors == []
    assert seen["exclude_entities"] == ["sensor.*"] and seen["exclude_devices"] == ["Hall*"], "filters ignored"
    shown = conn.results[0][1]["devices"]
    assert shown == [{"key": "d1", "name": "Jane's phone", "kind": "Apple", "area": "", "personal": True,
                      "entities": [{"entity_id": "device_tracker.jane", "platform": "device_tracker", "name": "Jane"}]}]
    assert "SECRET PLACE" not in json.dumps(shown)


@pytest.mark.parametrize("handler, msg", [
    (bring_in._ws_preview, {"type": bring_in.WS_PREVIEW, "upload_id": "u"}),
    (bring_in._ws_apply, {"type": bring_in.WS_APPLY, "upload_id": "u", "group": GROUP, "keys": ["a"]}),
    (bring_in._ws_forget, {"type": bring_in.WS_FORGET, "upload_id": "u"}),
    (bring_in._ws_export_review, {"type": bring_in.WS_EXPORT_REVIEW}),
])
def test_only_an_administrator_can_use_any_of_the_commands(tmp_path, handler, msg):
    hass, entry = ws_bench(tmp_path, {})
    up = upload(hass, {"a": device("Lamp", [light()])})
    msg = {**msg, **({"upload_id": up} if "upload_id" in msg else {})}
    conn = command(handler, hass, msg, admin=False)
    assert conn.results == [] and conn.errors == []
    assert conn.refused, "a non-administrator was let in"
    get_upload(hass, up)   # still held: nothing ran
    assert run(load_devices(entry.data["file_name"])) == {}


def test_every_command_and_the_upload_view_are_registered(monkeypatch):
    commands, views = [], []
    monkeypatch.setattr(bring_in.websocket_api, "async_register_command",
                        lambda hass, handler: commands.append(handler))
    hass = FakeHass()
    hass.http = type("Http", (), {"register_view": lambda self, view: views.append(view)})()
    bring_in.async_register_bring_in(hass)
    assert set(commands) == {bring_in._ws_preview, bring_in._ws_apply, bring_in._ws_forget,
                             bring_in._ws_export_review}
    assert [type(v) for v in views] == [bring_in.ImportUploadView]


def test_the_wire_names_are_the_ones_the_panel_uses():
    assert (bring_in.WS_PREVIEW, bring_in.WS_APPLY, bring_in.WS_FORGET, bring_in.WS_EXPORT_REVIEW) == (
        "virtual/import_preview", "virtual/import_apply", "virtual/import_forget", "virtual/export_review")
    assert bring_in.UPLOAD_URL == "/api/virtual/import_upload"


def test_what_the_panel_is_told_about_each_device_is_all_there():
    block = parsed({"d": device("Jane's phone", [
        {"platform": "device_tracker", "name": "Jane", "entity_id": "device_tracker.jane"}],
        manufacturer="Apple", model="iPhone", area="Hall")})["d"]
    assert summarise({"d": block}) == [{
        "key": "d", "name": "Jane's phone", "kind": "Apple iPhone", "area": "Hall", "personal": True,
        "entities": [{"entity_id": "device_tracker.jane", "platform": "device_tracker", "name": "Jane"}]}]
    only_maker = parsed({"e": device("X", [light()], manufacturer="Acme")})["e"]
    assert summarise({"e": only_maker})[0]["kind"] == "Acme"


# ─────────────────────────────────────────── what makes two devices the same

@pytest.mark.parametrize("key, one, other", [
    ("initial_availability", True, False), ("persistent", True, False),
    ("initial_brightness", 10, 200), ("initial_color", [1, 2], [3, 4]), ("initial_effect", "a", "b"),
    ("initial_value", "on", "off"), ("unique_id", "u1", "u2"),
])
def test_a_difference_in_the_moment_alone_does_not_make_a_different_device(key, one, other):
    first = parsed({"a": device("Lamp", [light(**{key: one})])})["a"]
    second = parsed({"b": device("Lamp", [light(**{key: other})])})["b"]
    assert classify(Index({"a": first}), "b", second)["status"] == "same", key


def test_another_model_is_a_different_device_and_the_order_of_parts_is_not():
    parts = [light("light.a", "A"), light("light.b", "B")]
    base = parsed({"a": device("Lamp", parts, manufacturer="Acme", model="L1")})["a"]
    other_model = parsed({"b": device("Lamp", parts, manufacturer="Acme", model="L2")})["b"]
    reordered = parsed({"c": device("Lamp", list(reversed(parts)), manufacturer="Acme", model="L1")})["c"]
    index = Index({"a": base})
    assert classify(index, "b", other_model)["status"] != "same"
    assert classify(index, "c", reordered)["status"] == "same"


def test_a_key_that_is_taken_gets_a_new_one_quietly_because_nobody_sees_keys():
    """Saying 'Two was added as Two' would be nonsense: the person sees names and ids."""
    here = parsed({"k": device("One", [light("light.one")])})
    there = parsed({"k": device("Two", [light("light.two", "Two")])})
    plan = classify(Index(here), "k", there["k"])
    assert plan == {"status": "new", "key": "k (2)", "name": "Two", "ids": {}}


def test_the_preview_gives_no_new_name_to_a_device_that_will_not_be_added():
    devices = parsed({"a": device("Lamp", [light()])})
    assert preview(devices, Index(devices))["a"]["name"] is None


# ───────────────────────────────────── what lands on disk after a clash

def test_a_numbered_device_is_saved_under_its_number_and_a_moved_entity_loses_its_old_unique_id(tmp_path):
    hass, entry = bench(tmp_path, {})
    first = upload(hass, {"a": device("Kitchen Light", [light()])})
    run(async_apply(hass, first, GROUP, None, ["a"], {}))
    second = upload(hass, {"b": device("Kitchen Light", [light(unique_id="light.kitchen.virtual",
                                                                 supported_color_modes=["hs"])])})
    run(async_apply(hass, second, GROUP, None, ["b"], {}))
    saved = run(load_devices(entry.data["file_name"]))
    assert sorted(block["name"] for block in saved.values()) == ["Kitchen Light", "Kitchen Light (2)"]
    moved = next(b for b in saved.values() if b["name"] == "Kitchen Light (2)")["entities"][0]
    assert moved["entity_id"] == "light.kitchen_2" and "unique_id" not in moved


def test_a_newcomer_that_moves_to_a_new_id_does_not_land_on_one_a_later_newcomer_has(tmp_path):
    """light.a clashes and is moved to light.a_2, which the next newcomer already calls
    itself: the first one's NEW id has to count as taken."""
    hass, entry = bench(tmp_path, {})
    run(async_apply(hass, upload(hass, {"x": device("First", [light("light.a", "A")])}), GROUP, None, ["x"], {}))
    batch = upload(hass, {"b": device("Second", [light("light.a", "B")]),
                          "c": device("Third", [light("light.a_2", "C")])})
    run(async_apply(hass, batch, GROUP, None, ["b", "c"], {}))
    ids = sorted(e["entity_id"] for block in run(load_devices(entry.data["file_name"])).values()
                 for e in block["entities"])
    assert len(ids) == 3 and len(set(ids)) == 3, ids


def test_two_identical_copies_that_clash_with_a_different_device_are_added_once(tmp_path):
    hass, entry = bench(tmp_path, {"mine": [light("light.lamp", "Mine", supported_color_modes=["hs"])]})
    up = upload(hass, {"a": device("Lamp", [light("light.lamp", "Lamp")]),
                       "b": device("Lamp", [light("light.lamp", "Lamp")])})
    result = run(async_apply(hass, up, GROUP, None, ["a", "b"], {}))
    assert len(result["added"]) == 1 and len(result["same"]) == 1, result


def test_the_result_says_which_group_it_went_to_and_what_matched_what(tmp_path):
    hass, entry = bench(tmp_path, {})
    run(async_apply(hass, upload(hass, {"a": device("Lamp", [light()])}), GROUP, None, ["a"], {}))
    result = run(async_apply(hass, upload(hass, {"z": device("Lamp", [light()]), "y": device("Fan", [
        {"platform": "fan", "name": "Fan", "entity_id": "fan.f"}])}), GROUP, None, ["z", "y"], {}))
    assert result == {"group": GROUP, "added": ["Fan"], "same": [{"name": "Lamp", "same_as": "Lamp"}],
                      "renamed": []}


# ──────────────────────────────────────────────── reading odd files and names

def test_entities_without_ids_do_not_clash_with_each_other():
    check_ids_unique({"d": {"name": "X", "entities": [
        {"platform": "light", "name": "A"}, {"platform": "light", "name": "B"}]}})


def test_an_entity_that_is_not_a_mapping_or_has_no_text_platform_is_left_out_not_a_crash():
    text = yaml.safe_dump({"devices": {"d": {"name": "X", "entities": [
        "just text", 5, {"platform": 7, "entity_id": "light.x"}, {"platform": "light", "entity_id": "light.ok"}]}}})
    assert [e["entity_id"] for e in parse_export(text)["devices"]["d"]["entities"]] == ["light.ok"]


def test_a_blank_name_box_does_not_wipe_a_name_and_retyping_an_id_changes_nothing():
    block = parsed({"d": device("Lamp", [light(unique_id="light.kitchen.virtual")])})["d"]
    same = apply_renames("d", block, {"entities": {"light.kitchen": {"name": "   ", "entity_id": "light.kitchen"}}})
    assert same == block, "nothing was changed, so nothing may be dropped (not even the unique id)"


# ─────────────────────────────────────────────────────────── the upload endpoint, more

def test_the_endpoint_demands_a_login_and_a_user():
    assert bring_in.ImportUploadView.requires_auth is True
    request = Body(b"x", None)
    assert run(bring_in.ImportUploadView().post(request)).status == 403, "no user must be refused, not crash"


def test_a_file_of_exactly_the_limit_is_accepted_and_one_byte_more_is_not():
    head = export_text({"a": device("Lamp", [light()])})
    exact = head + "#" * (bring_in.UPLOAD_LIMIT - len(head.encode()) - 1) + "\n"
    assert len(exact.encode()) == bring_in.UPLOAD_LIMIT
    assert post(exact.encode())[0].status == 200
    assert post(exact.encode() + b"#")[0].status == 413


def test_the_file_is_read_off_the_event_loop_and_its_source_comes_back():
    request = Body(export_text({"a": device("Lamp", [light()])}).encode(), User(True))
    hass = request.app[bring_in.KEY_HASS]
    ran = []
    inner = hass.async_add_executor_job

    async def spy(func, *args):
        ran.append(func)
        return await inner(func, *args)

    hass.async_add_executor_job = spy
    reply = run(bring_in.ImportUploadView().post(request))
    assert ran == [bring_in.parse_export], "parsing a big file must not block Home Assistant"
    assert json.loads(reply.text)["source"].startswith("Exported by Virtual Test Devices")


def test_a_swept_file_is_really_gone_from_memory(monkeypatch):
    hass = FakeHass()
    now = [0.0]
    monkeypatch.setattr(bring_in.time, "monotonic", lambda: now[0])
    old = put_upload(hass, {"source": "", "devices": {}})
    now[0] += bring_in.UPLOAD_LIFETIME + 1
    new = put_upload(hass, {"source": "", "devices": {}})
    assert list(hass.data[bring_in._UPLOADS]) == [new] and old not in hass.data[bring_in._UPLOADS]


# ───────────────────────────────────────────────── making a group, against a stand-in flow

class FakeFlow:
    def __init__(self, result):
        self.result, self.calls = result, []

    async def async_init(self, domain, context=None, data=None):
        self.calls.append((domain, context, data))
        return self.result


def flow_hass(tmp_path, result):
    from homeassistant.data_entry_flow import FlowResultType
    hass = FakeHass(config_dir=tmp_path)
    hass.config_entries.flow = FakeFlow(result if result is not None else {"type": FlowResultType.CREATE_ENTRY})
    return hass


@pytest.mark.parametrize("name, file_name", [
    ("Sam's House!", "virtual_sam_s_house.yaml"), ("  Dana  ", "virtual_dana.yaml"),
    ("!!!", "virtual_imported.yaml"), ("Ünï 2", "virtual_n_2.yaml"),
])
def test_a_new_group_gets_a_safe_file_name_made_from_its_name(tmp_path, name, file_name):
    hass = flow_hass(tmp_path, None)
    run(bring_in._create_group(hass, name))
    domain, context, data = hass.config_entries.flow.calls[0]
    assert (domain, context) == (COMPONENT_DOMAIN, {"source": "user"})
    assert data == {"group_name": name, "file_name": str(tmp_path / file_name)}


def test_a_new_group_never_takes_over_a_file_that_is_already_there(tmp_path):
    (tmp_path / "virtual_sam.yaml").write_text("devices: {}\n")
    (tmp_path / "virtual_sam_2.yaml").write_text("devices: {}\n")
    hass = flow_hass(tmp_path, None)
    run(bring_in._create_group(hass, "Sam"))
    assert hass.config_entries.flow.calls[0][2]["file_name"] == str(tmp_path / "virtual_sam_3.yaml")


@pytest.mark.parametrize("result, wanted", [
    ({"type": "form", "errors": {"base": "group_name_used"}}, "group name used"),
    ({"type": "abort", "reason": "export_only"}, "export only"),
    ({"type": "form"}, "it was refused"),
])
def test_a_group_the_flow_refuses_is_reported_in_words(tmp_path, result, wanted):
    from homeassistant.data_entry_flow import FlowResultType
    hass = flow_hass(tmp_path, {**result, "type": FlowResultType(result["type"])})
    with pytest.raises(BringInError, match=wanted):
        run(bring_in._create_group(hass, "Sam"))
