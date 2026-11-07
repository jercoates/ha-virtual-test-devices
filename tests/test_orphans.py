"""Removing something from the file removes THAT, and only that.

REGRESSION GUARD. The old orphan handling deleted the orphan's whole DEVICE. A
device with three entities that lost one therefore lost all three, was recreated
under a new id at platform setup, and forgot its area and customisations — and
anything that referred to it by device id broke.

Now the file is the source of truth: an entity row whose unique id the file no
longer lists is removed one at a time, and a device goes only when the file no
longer lists the device.
"""

import custom_components.virtual as virtual


class Row:
    def __init__(self, entity_id, unique_id):
        self.entity_id, self.unique_id = entity_id, unique_id


class Device:
    def __init__(self, ident, name):
        self.id, self.name, self.identifiers = f"id-{ident}", name, {("virtual", ident)}


class Registries:
    """Stands in for both registries and records what was removed."""

    def __init__(self, rows, devices):
        self.rows, self.devices = rows, devices
        self.removed_entities, self.removed_devices = [], []

    def async_remove(self, entity_id):
        self.removed_entities.append(entity_id)

    def async_remove_device(self, device_id):
        self.removed_devices.append(device_id)


class Cfg:
    def __init__(self, entities, devices, trusted=True, file_missing=False):
        self.entities = {"switch": [{"unique_id": u} for u in entities]}
        self.devices = [{"device_id": d} for d in devices]
        self.trusted = trusted
        self.file_missing = file_missing


class Entry:
    entry_id = "e1"


def _run(monkeypatch, rows, devices, file_entities, file_devices, trusted=True,
         file_missing=False):
    regs = Registries(rows, devices)
    monkeypatch.setattr(virtual.er, "async_get", lambda hass: regs)
    monkeypatch.setattr(virtual.er, "async_entries_for_config_entry", lambda reg, eid: regs.rows)
    monkeypatch.setattr(virtual.dr, "async_get", lambda hass: regs)
    monkeypatch.setattr(virtual.dr, "async_entries_for_config_entry", lambda reg, eid: regs.devices)
    virtual._async_remove_orphans(
        None, Entry(), Cfg(file_entities, file_devices, trusted, file_missing))
    return regs


ROWS = [Row("switch.a", "ua"), Row("switch.b", "ub"), Row("switch.c", "uc")]
DEVICES = [Device("d1", "One"), Device("d2", "Two")]


def test_nothing_is_removed_when_the_file_still_has_everything(monkeypatch):
    """The control: without it, 'it removed the right thing' proves nothing."""
    regs = _run(monkeypatch, ROWS, DEVICES, ["ua", "ub", "uc"], ["d1", "d2"])
    assert regs.removed_entities == [] and regs.removed_devices == []


def test_a_dropped_entity_goes_alone_and_its_device_stays(monkeypatch):
    regs = _run(monkeypatch, ROWS, DEVICES, ["ua", "uc"], ["d1", "d2"])
    assert regs.removed_entities == ["switch.b"]
    assert regs.removed_devices == []  # its siblings, and the device, survive


def test_a_dropped_device_is_removed(monkeypatch):
    regs = _run(monkeypatch, ROWS, DEVICES, ["ua", "ub", "uc"], ["d1"])
    assert regs.removed_devices == ["id-d2"]


def test_an_entity_the_file_never_listed_is_removed(monkeypatch):
    """A stand-in dropped from a re-exported file has no meta row to be noticed
    through, so the registry itself has to be the check."""
    regs = _run(monkeypatch, ROWS + [Row("switch.ghost", "ughost")], DEVICES,
                ["ua", "ub", "uc"], ["d1", "d2"])
    assert regs.removed_entities == ["switch.ghost"]


def test_nothing_is_removed_when_the_file_could_not_be_trusted(monkeypatch):
    """An unreadable or half-written file reads as 'lists nothing'. Acting on that
    would remove every row in the group, and they would come back under new ids."""
    regs = _run(monkeypatch, ROWS, DEVICES, [], [], trusted=False)
    assert regs.removed_entities == [] and regs.removed_devices == []


def test_nothing_is_removed_when_the_file_has_gone_missing(monkeypatch):
    """A bind mount that did not come up, or a file renamed, reads as a missing
    file. For a group that already has rows that is not a new group, and acting on
    'lists nothing' would remove all of them."""
    regs = _run(monkeypatch, ROWS, DEVICES, [], [], file_missing=True)
    assert regs.removed_entities == [] and regs.removed_devices == []


def test_a_missing_file_is_fine_for_a_group_that_owns_nothing(monkeypatch):
    """The control: a brand-new group has no file yet and must still load, and
    there is nothing for it to remove either way."""
    regs = _run(monkeypatch, [], [], [], [], file_missing=True)
    assert regs.removed_entities == [] and regs.removed_devices == []


def test_a_missing_file_with_only_device_rows_removes_nothing_either(monkeypatch):
    """A group whose devices have no entities left still owns those devices, and a
    vanished file must not remove them."""
    regs = _run(monkeypatch, [], DEVICES, [], [], file_missing=True)
    assert regs.removed_entities == [] and regs.removed_devices == []
