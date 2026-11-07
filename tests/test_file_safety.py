"""Saving and loading the group's device file.

REGRESSION GUARD. The savers used to open the real file in 'w' — which truncates
it to zero — and only THEN serialize, swallowing any failure at debug level. One
value yaml couldn't represent therefore emptied the file, destroyed every test
device, and left the integration unable to load, silently. It happened for real
on the bench.

These tests fail if a save can ever damage an existing file, or if an unreadable
file can take the integration down again.
"""

import logging

import pytest

from conftest import FakeEntry, FakeHass, load_devices, run

from custom_components.virtual.cfg import (
    BlendedCfg,
    MetaFileError,
    _async_load_json,
    _async_load_yaml,
    _async_read_user_file,
    _async_save_yaml,
    _save_user_data,
)


class Unserialisable:
    """yaml has no representer for this."""


def test_failed_save_leaves_the_existing_file_intact(tmp_path):
    """THE data-loss bug: a bad value must not destroy what's already there."""
    path = str(tmp_path / "virtual.yaml")
    good = {"version": 1, "devices": {"Keep Me": [{"platform": "switch", "name": "Keep Me"}]}}
    run(_async_save_yaml(path, good))
    before = open(path, encoding="utf-8").read()
    assert before.strip()

    with pytest.raises(Exception):
        run(_async_save_yaml(path, {"version": 1, "devices": {"Bad": Unserialisable()}}))

    after = open(path, encoding="utf-8").read()
    assert after == before, "a failed save damaged the existing file"
    assert run(_async_load_yaml(path)) == good


def test_failed_save_raises_rather_than_going_quiet(tmp_path):
    """It used to be swallowed at debug level, so nothing reported the loss."""
    path = str(tmp_path / "virtual.yaml")
    with pytest.raises(Exception):
        run(_async_save_yaml(path, {"devices": {"Bad": Unserialisable()}}))


def test_empty_file_degrades_to_no_devices(tmp_path):
    """An empty file parses to None, and `.get` on it used to kill setup."""
    path = tmp_path / "virtual.yaml"
    path.write_text("", encoding="utf-8")
    assert run(load_devices(str(path))) == {}


def test_unparseable_file_degrades_to_no_devices(tmp_path):
    path = tmp_path / "virtual.yaml"
    path.write_text("devices:\n  - [unclosed\n   bad: : :\n", encoding="utf-8")
    assert run(load_devices(str(path))) == {}


def test_non_mapping_file_degrades_to_no_devices(tmp_path):
    path = tmp_path / "virtual.yaml"
    path.write_text("just a bare string\n", encoding="utf-8")
    assert run(load_devices(str(path))) == {}


def test_missing_file_degrades_to_no_devices(tmp_path):
    assert run(load_devices(str(tmp_path / "does-not-exist.yaml"))) == {}


def test_round_trip_preserves_devices(tmp_path):
    path = str(tmp_path / "virtual.yaml")
    devices = {
        "Thermostat": [{"platform": "climate", "name": "Thermostat",
                        "supported_features": 155,
                        "hvac_modes": ["off", "heat", "cool"],
                        "min_temp": 4.4, "max_temp": 95.0}],
        "Speaker": [{"platform": "media_player", "name": "Speaker",
                     "source_list": ["Line-in", "Radio"]}],
    }
    run(_save_user_data(path, devices))
    assert run(load_devices(path)) == devices


def test_no_temp_file_is_left_behind(tmp_path):
    """The atomic write uses a .tmp alongside; it must not survive."""
    path = tmp_path / "virtual.yaml"
    run(_save_user_data(str(path), {"A": [{"platform": "switch", "name": "A"}]}))
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert not leftovers, leftovers


# --- the identity (meta) file ------------------------------------------------


def test_a_missing_identity_file_is_a_new_install(tmp_path):
    assert run(_async_load_json(str(tmp_path / "virtual.meta.json"))) == {}


@pytest.mark.parametrize("damage", ["", "{not json", "[1, 2]"])
def test_a_damaged_identity_file_is_an_error_not_empty(tmp_path, damage):
    """Read as empty, every entity looks new and gets a fresh unique id, the old
    registry rows are removed as orphans, and the damaged file is overwritten."""
    path = tmp_path / "virtual.meta.json"
    path.write_text(damage)
    with pytest.raises(MetaFileError):
        run(_async_load_json(str(path)))
    assert path.read_text() == damage


# --- what the reader believes -------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("devices:\n", ({}, True)),               # left empty: no devices, believable
    ("devices: {}\n", ({}, True)),            # the deliberate way to say it
    ("version: 1\n", ({}, True)),             # a marker alone is not a device
    ("devices: [a, b]\n", ({}, False)),       # not a mapping: not believable
])
def test_what_the_reader_believes(tmp_path, text, expected):
    path = tmp_path / "virtual.yaml"
    path.write_text(text)
    assert run(_async_read_user_file(str(path))) == expected


def test_an_empty_file_is_not_believed_and_says_so(tmp_path, caplog):
    """It used to be refused with 'see the log' and nothing in the log."""
    path = tmp_path / "virtual.yaml"
    path.write_text("")
    with caplog.at_level(logging.WARNING):
        assert run(_async_read_user_file(str(path))) == ({}, False)
    assert "is empty" in caplog.text and "devices: {}" in caplog.text


def test_the_loader_knows_a_file_is_missing_as_opposed_to_unreadable(tmp_path):
    """The orphan guard rests on this being computed, not on a stub saying so."""
    path = tmp_path / "virtual.yaml"

    missing = BlendedCfg(FakeHass(config_dir=tmp_path), FakeEntry(path).data)
    run(missing.async_load())
    assert missing.file_missing and missing.trusted

    path.write_text("devices: {}\n")
    present = BlendedCfg(FakeHass(config_dir=tmp_path), FakeEntry(path).data)
    run(present.async_load())
    assert not present.file_missing

    path.write_text("")
    blank = BlendedCfg(FakeHass(config_dir=tmp_path), FakeEntry(path).data)
    run(blank.async_load())
    assert not blank.file_missing and not blank.trusted
