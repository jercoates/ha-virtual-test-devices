"""Bring devices in from an export file, and the name review both ends share.

An export (export.py) describes a whole Home Assistant. This reads one back,
lists its devices, and adds the ones chosen to a group here, so a developer can
bring in several people's devices at once to reproduce what they see.

The rules, which the panel only displays:

  * A device that is IDENTICAL to one already in ANY group (same name, same entity
    ids, same abilities; the current state does not count) is offered once and not
    added again, however many files carry it. Entity ids belong to the whole Home
    Assistant, so every group is compared, not only the one being written to.
  * A device with the same name but anything different is added with a number:
    `Kitchen Light (2)`. The same for an entity id that is already used:
    `light.kitchen_2`. Nothing is ever replaced.
  * Names are NOT stripped automatically. A program cannot tell a person's name
    from a room called "Living Room", and an entity id carries the name too, so the
    sender is warned and given a box to rename anything (`apply_renames`), at
    export and again here. Names inside an entity's attribute text are not covered,
    and the warning says so.

An uploaded file is held in memory only, for half an hour, and never written to
disk. Everything here is administrator only.
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from http import HTTPStatus

import voluptuous as vol
import yaml

from homeassistant.components import websocket_api
from homeassistant.components.http import KEY_HASS, KEY_HASS_USER, HomeAssistantView
from homeassistant.const import ATTR_ENTITY_ID, CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from .cfg import _async_read_user_file, _device_block
from .const import *
from .pistoncore_manage import _find_entry, _mutate_and_reload, check_entries, free_device_name

_LOGGER = logging.getLogger(__name__)

WS_PREVIEW = "virtual/import_preview"
WS_APPLY = "virtual/import_apply"
WS_FORGET = "virtual/import_forget"
WS_EXPORT_REVIEW = "virtual/export_review"

UPLOAD_URL = "/api/virtual/import_upload"
UPLOAD_LIMIT = 15 * 1024 * 1024   # Home Assistant itself refuses a request over 16 MiB
UPLOAD_LIFETIME = 30 * 60
MAX_UPLOADS = 8
_UPLOADS = "virtual_import_uploads"
_LOCK = "virtual_import_lock"
# yaml lets a few lines stand for a structure of any size (a name that is a list of lists of
# lists ... each repeated nine times). A real export holds well under this many values.
EXPANDED_LIMIT = 3_000_000

# What an entry says about the moment it was exported rather than about the device.
# Two lamps that differ only in being on or off are the same lamp.
MOMENT_KEYS = {"initial_value", "initial_availability", "persistent", "unique_id",
               "initial_brightness", "initial_color", "initial_effect"}
# Which of a device's details make it a different device (the firmware and the room
# do not: the same bulb in two houses is the same bulb).
IDENTITY_META = ("manufacturer", "model")

ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
# Rows the panel marks as "may carry a person's name". A hint only, never acted on.
PERSON_PLATFORMS = {"person", "device_tracker"}


class BringInError(ValueError):
    """A problem the person can fix; the message is shown to them as it is."""


# What a typed-over name looks like on the wire, from the panel and from the export action.
RENAMES_SCHEMA = vol.Schema({
    vol.Optional("devices", default=dict): {str: str},
    vol.Optional("entities", default=dict): {
        str: {vol.Optional("name"): str, vol.Optional("entity_id"): str}},
})


# ------------------------------------------------------------------ reading a file

def _check_expanded(value) -> None:
    """Refuse a structure that is far bigger than the file that described it. Counted by
    walking it, and stopped early, so a hostile file costs a moment and not the machine."""
    seen, stack = 0, [value]
    while stack:
        item = stack.pop()
        seen += 1
        if seen > EXPANDED_LIMIT:
            raise BringInError("That file is not an export: it stands for far more than "
                               "a real one can hold.")
        if isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, (list, tuple, set)):
            stack.extend(item)


def parse_export(text: str) -> dict:
    """{"source": the export's own header line, "devices": {key: block}}.

    A block is {"name", optional manufacturer/model/sw_version/area, "entities"}.
    Plain yaml only: no tags, so a file cannot make this read anything else."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        raise BringInError("That file is not an export: it is not valid yaml.") from None
    _check_expanded(parsed)
    if not isinstance(parsed, dict):
        raise BringInError("That file is not an export: it does not hold a list of devices.")
    raw = parsed[ATTR_DEVICES] if ATTR_DEVICES in parsed else {
        k: v for k, v in parsed.items() if k != ATTR_VERSION}
    if not isinstance(raw, dict):
        raise BringInError("That file is not an export: its devices are not in the usual form.")
    devices = {}
    for key, block in raw.items():
        entities, meta = _device_block(str(key), block)
        entities = [dict(e) for e in entities
                    if isinstance(e, dict) and isinstance(e.get(CONF_PLATFORM), str)]
        for entity in entities:
            # Home Assistant makes ids lower case, so an id is compared in lower case; an
            # id that is not text cannot be one.
            entity_id = entity.get(ATTR_ENTITY_ID)
            if isinstance(entity_id, str):
                entity[ATTR_ENTITY_ID] = entity_id.strip().lower()
            elif entity_id is not None:
                del entity[ATTR_ENTITY_ID]
        if not entities:
            continue
        name = meta.pop("name", None) or str(key)
        devices[str(key)] = {"name": str(name), **meta, "entities": entities}
    if not devices:
        raise BringInError("There are no devices in that file.")
    header = next((line.lstrip("# ").strip() for line in text.splitlines()
                   if line.startswith("# Exported by")), "")
    return {"source": header, "devices": devices}


def _kind(block) -> str:
    return " ".join(p for p in (block.get("manufacturer"), block.get("model")) if p)


def looks_personal(block) -> bool:
    """True when something in the device is likely to carry a person's name."""
    for entity in block["entities"]:
        entity_id = str(entity.get(ATTR_ENTITY_ID) or "")
        if (entity.get(CONF_PLATFORM) in PERSON_PLATFORMS
                or (entity.get(CONF_PLATFORM) == "notify" and "mobile_app_" in entity_id)):
            return True
    return False


def summarise(devices: dict) -> list:
    """What the panel is shown: names, kinds and entity ids. Never a state or any
    other setting (a tracker's starting state is a place)."""
    return [{
        "key": key,
        "name": block["name"],
        "kind": _kind(block),
        "area": block.get("area") or "",
        "personal": looks_personal(block),
        "entities": [{"entity_id": e.get(ATTR_ENTITY_ID) or "", "platform": e[CONF_PLATFORM],
                      "name": str(e.get(CONF_NAME) or "")} for e in block["entities"]],
    } for key, block in devices.items()]


# ------------------------------------------------------------------------ renaming

def apply_renames(key, block, renames):
    """A copy of `block` with the names the person typed. `renames` is
    {"devices": {device key: new name}, "entities": {entity id: {"name", "entity_id"}}}
    keyed by what the file called things; a blank box means no change."""
    renames = renames or {}
    new = {k: v for k, v in block.items() if k != "entities"}
    wanted = str((renames.get("devices") or {}).get(key) or "").strip()
    if wanted:
        new["name"] = wanted
    by_entity = renames.get("entities") or {}
    entities = []
    for entity in block["entities"]:
        entry = dict(entity)
        change = by_entity.get(entity.get(ATTR_ENTITY_ID)) or {}
        name = str(change.get("name") or "").strip()
        if name:
            entry[CONF_NAME] = name
        entity_id = str(change.get("entity_id") or "").strip().lower()
        if entity_id and entity_id != entry.get(ATTR_ENTITY_ID):
            if not ID_PATTERN.match(entity_id) or entity_id.split(".")[0] != entry[CONF_PLATFORM]:
                raise BringInError(
                    f"'{entity_id}' cannot be used: an id is lower case letters, digits and "
                    f"underscores, and a {entry[CONF_PLATFORM]} must start with "
                    f"'{entry[CONF_PLATFORM]}.'")
            entry[ATTR_ENTITY_ID] = entity_id
            entry.pop(ATTR_UNIQUE_ID, None)   # it was made from the old id
        entities.append(entry)
    new["entities"] = entities
    return new


def renamed_key(key, renames):
    """A device that is only one entity is filed under that entity's id. If the person
    renamed the id, the old one must not survive as the key."""
    change = ((renames or {}).get("entities") or {}).get(key) or {}
    new = str(change.get("entity_id") or "").strip().lower()
    return new if new and ID_PATTERN.match(new) else key


def rekey(devices: dict, renames) -> dict:
    """`devices` with `renamed_key` applied to every key (two ending up the same is an error)."""
    out = {}
    for key, block in devices.items():
        final = renamed_key(key, renames)
        if final in out:
            raise BringInError(f"Two devices would be filed under '{final}'. Give one of them another id.")
        out[final] = block
    return out


def check_ids_unique(devices: dict) -> None:
    """No two entities may end up with the same id after renaming."""
    seen = {}
    for block in devices.values():
        for entity in block["entities"]:
            entity_id = entity.get(ATTR_ENTITY_ID)
            if not entity_id:
                continue
            if entity_id in seen:
                raise BringInError(
                    f"Two things would be called '{entity_id}' ('{seen[entity_id]}' and "
                    f"'{entity.get(CONF_NAME)}'). Give one of them another id.")
            seen[entity_id] = entity.get(CONF_NAME)


# ----------------------------------------------------------- same, or a different one

def fingerprint(name, meta, entities) -> str:
    """Two devices with the same fingerprint are the same device."""
    shape = sorted(
        ({k: v for k, v in e.items() if k not in MOMENT_KEYS} for e in entities),
        key=lambda e: (str(e.get(ATTR_ENTITY_ID) or ""), str(e.get(CONF_PLATFORM)),
                       str(e.get(CONF_NAME))))
    return json.dumps([name, [meta.get(k) for k in IDENTITY_META], shape],
                      sort_keys=True, default=str)


def distinct(devices: dict) -> dict:
    """`devices` without the later copies of a device that is identical to an earlier
    one: those are added once, so they cannot be said to share an id."""
    seen, out = set(), {}
    for key, block in devices.items():
        meta = {k: block.get(k) for k in IDENTITY_META}
        copy = fingerprint(block["name"], meta, block["entities"])
        if copy not in seen:
            seen.add(copy)
            out[key] = block
    return out


class Index:
    """What the groups already hold, so a newcomer can be told apart from a copy.

    Built from EVERY group, not just the one being written to: an entity id belongs
    to the whole Home Assistant, and so does a device's key, so the same id in two
    groups would leave one of them without its entity."""

    def __init__(self, *group_devices: dict):
        self.keys, self.names, self.fingerprints, self.ids = set(), set(), {}, set()
        for devices in group_devices:
            for key, block in (devices or {}).items():
                entities, meta = _device_block(str(key), block)
                self.add(str(key), meta.get("name") or str(key), meta, entities)

    def add(self, key, name, meta, entities) -> None:
        self.keys.add(key)
        self.names.add(name)
        self.fingerprints.setdefault(fingerprint(name, meta, entities), name)
        self.ids.update(e[ATTR_ENTITY_ID] for e in entities
                        if isinstance(e, dict) and e.get(ATTR_ENTITY_ID))


def _free_id(taken: set, entity_id: str) -> str:
    domain, _, tail = entity_id.partition(".")
    number = 2
    while f"{domain}.{tail}_{number}" in taken:
        number += 1
    return f"{domain}.{tail}_{number}"


def classify(index: Index, key, block) -> dict:
    """{"status": "same", "same_as"} or {"status": "new"|"renamed", "key", "name",
    "ids": {old id: new id}}. "renamed" means something clashed and got a number."""
    meta = {k: block.get(k) for k in IDENTITY_META}
    found = index.fingerprints.get(fingerprint(block["name"], meta, block["entities"]))
    if found is not None:
        return {"status": "same", "same_as": found}
    name = free_device_name(index.names, block["name"])
    final_key = free_device_name(index.keys, key)
    # A new id must clear what the group uses AND what this device's own entities use.
    taken = index.ids | {e.get(ATTR_ENTITY_ID) for e in block["entities"]}
    ids = {}
    for entity in block["entities"]:
        entity_id = entity.get(ATTR_ENTITY_ID)
        if entity_id and entity_id in index.ids:
            ids[entity_id] = _free_id(taken, entity_id)
            taken.add(ids[entity_id])
    # The key is internal and never shown, so a key that merely had to change is not a rename.
    clashed = name != block["name"] or bool(ids)
    return {"status": "renamed" if clashed else "new", "key": final_key, "name": name,
            "ids": ids}


def _block_to_write(block, plan) -> dict:
    entities = []
    for entity in block["entities"]:
        entry = dict(entity)
        moved = plan["ids"].get(entry.get(ATTR_ENTITY_ID))
        if moved:
            entry[ATTR_ENTITY_ID] = moved
            entry.pop(ATTR_UNIQUE_ID, None)
        entities.append(entry)
    return {**{k: v for k, v in block.items() if k not in ("entities", "name")},
            CONF_NAME: plan["name"], ATTR_ENTITIES: entities}


def plan_batch(chosen: dict, index: Index) -> tuple:
    """([(plan, block)] to add, [(block, plan)] already here). Adds to `index` as it goes, so
    a later device is compared with the earlier ones in the same batch."""
    to_add, same = [], []
    for key, block in chosen.items():
        plan = classify(index, key, block)
        if plan["status"] == "same":
            same.append((block, plan))
            continue
        written = _block_to_write(block, plan)
        meta = {k: block.get(k) for k in IDENTITY_META}
        index.add(plan["key"], plan["name"], meta, written[ATTR_ENTITIES])
        # An identical copy later in the batch must be recognised as the device as it was
        # sent, not only as the numbered one that was written: otherwise two copies of the
        # same lamp that clash with one already here become "Lamp (2)" and "Lamp (3)".
        index.fingerprints.setdefault(fingerprint(block["name"], meta, block["entities"]), plan["name"])
        to_add.append((plan, block, written))
    return to_add, same


def preview(parsed_devices: dict, index: Index) -> dict:
    """For each device in the file: what bringing it in would do."""
    seen = {}
    out = {}
    for key, block in parsed_devices.items():
        plan = classify(index, key, block)
        meta = {k: block.get(k) for k in IDENTITY_META}
        fp = fingerprint(block["name"], meta, block["entities"])
        if plan["status"] != "same" and fp in seen:
            plan = {"status": "same", "same_as": seen[fp]}
        seen.setdefault(fp, block["name"])
        out[key] = {"status": plan["status"], "same_as": plan.get("same_as"),
                    "name": plan.get("name"),
                    "ids": plan.get("ids") or {}}
    return out


# -------------------------------------------------------------------------- uploads

def put_upload(hass: HomeAssistant, parsed: dict) -> str:
    store = hass.data.setdefault(_UPLOADS, {})
    now = time.monotonic()
    for key in [k for k, v in store.items() if now - v["at"] > UPLOAD_LIFETIME]:
        del store[key]
    while len(store) >= MAX_UPLOADS:
        del store[min(store, key=lambda k: store[k]["at"])]
    upload_id = uuid.uuid4().hex
    store[upload_id] = {**parsed, "at": now}
    return upload_id


def get_upload(hass: HomeAssistant, upload_id: str) -> dict:
    found = hass.data.get(_UPLOADS, {}).get(upload_id)
    if found is None or time.monotonic() - found["at"] > UPLOAD_LIFETIME:
        raise BringInError("That file is no longer held. Choose it again.")
    return found


class ImportUploadView(HomeAssistantView):
    """POST the text of an export; get back its devices and an id to refer to it by."""

    url = UPLOAD_URL
    name = "api:virtual:import_upload"
    requires_auth = True

    async def post(self, request):
        user = request.get(KEY_HASS_USER)
        if user is None or not user.is_admin:
            return self.json_message("Administrators only.", HTTPStatus.FORBIDDEN)
        hass = request.app[KEY_HASS]
        if hass.data.get(COMPONENT_CONFIG, {}).get(CONF_EXPORT_ONLY):
            return self.json_message("This Home Assistant is set to export only, so nothing can "
                                     "be brought in.", HTTPStatus.BAD_REQUEST)
        body = await request.read()
        if len(body) > UPLOAD_LIMIT:
            return self.json_message("That file is too large (the limit is 15 MB).",
                                     HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return self.json_message("That file is not text.", HTTPStatus.BAD_REQUEST)
        try:
            parsed = await hass.async_add_executor_job(parse_export, text)
        except BringInError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json({"upload_id": put_upload(hass, parsed),
                          "source": parsed["source"],
                          "devices": summarise(parsed["devices"])})


# --------------------------------------------------------------------------- applying

async def _all_groups(hass: HomeAssistant, skip=None) -> list:
    """The devices of every group (except `skip`), read from their files. A file that
    cannot be read stops the comparison: its ids are unknown, and guessing is how a
    device is lost."""
    maps = []
    for entry in hass.config_entries.async_entries(COMPONENT_DOMAIN):
        if skip is not None and entry.entry_id == skip.entry_id:
            continue
        devices, trusted = await _async_read_user_file(entry.data[ATTR_FILE_NAME])
        if not trusted:
            raise BringInError(
                f"The group '{entry.data.get(ATTR_GROUP_NAME)}' has a devices file that could "
                "not be read, so its devices cannot be compared with these. Fix it first.")
        maps.append(devices)
    return maps


async def _create_group(hass: HomeAssistant, name: str) -> None:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "imported"
    number, file_name = 1, hass.config.path(f"virtual_{slug}.yaml")
    while await hass.async_add_executor_job(os.path.exists, file_name):
        number += 1
        file_name = hass.config.path(f"virtual_{slug}_{number}.yaml")
    result = await hass.config_entries.flow.async_init(
        COMPONENT_DOMAIN, context={"source": "user"},
        data={ATTR_GROUP_NAME: name, ATTR_FILE_NAME: file_name})
    if result["type"] != FlowResultType.CREATE_ENTRY:
        why = (result.get("errors") or {}).get("base") or result.get("reason") or "it was refused"
        raise BringInError(f"Could not make the group '{name}': {why.replace('_', ' ')}.")


async def async_apply(hass: HomeAssistant, upload_id, group, new_group, keys, renames) -> dict:
    """Add the chosen devices to `group` (or to a group made for them). One reload.

    One import at a time, for the whole Home Assistant: the comparison reads EVERY group's
    file, and two imports into different groups each comparing against files the other had
    not written yet left the same entity id in both."""
    if hass.data.get(COMPONENT_CONFIG, {}).get(CONF_EXPORT_ONLY):
        raise BringInError("This Home Assistant is set to export only, so nothing can be brought in.")
    parsed = get_upload(hass, upload_id)
    unknown = [k for k in keys if k not in parsed["devices"]]
    if unknown:
        raise BringInError("Some of the chosen devices are not in that file any more.")
    if not keys:
        raise BringInError("No devices are ticked.")
    chosen = rekey({k: apply_renames(k, parsed["devices"][k], renames)
                    for k in dict.fromkeys(keys)}, renames)
    check_ids_unique(distinct(chosen))
    await check_entries(hass, [e for b in chosen.values() for e in b["entities"]])

    outcome = {"group": None, "added": [], "same": [], "renamed": []}
    lock = hass.data.setdefault(_LOCK, asyncio.Lock())
    async with lock:
        if new_group:
            # Find out BEFORE making the group whether anything would go into it: a group left
            # empty by a refused import blocks the same name next time.
            if not plan_batch(chosen, Index(*await _all_groups(hass)))[0]:
                raise BringInError("Every ticked device is already here, so nothing was added.")
            await _create_group(hass, new_group)
            group = new_group
        entry = _find_entry(hass, group)
        elsewhere = await _all_groups(hass, skip=entry)
        outcome["group"] = entry.data.get(ATTR_GROUP_NAME)

        def _add(devices):
            to_add, same = plan_batch(chosen, Index(devices, *elsewhere))
            outcome["same"] = [{"name": block["name"], "same_as": plan["same_as"]}
                               for block, plan in same]
            if not to_add:
                raise BringInError("Every ticked device is already here, so nothing was added.")
            for plan, block, written in to_add:
                devices[plan["key"]] = written
                outcome["added"].append(plan["name"])
                if plan["status"] == "renamed":
                    outcome["renamed"].append({"was": block["name"], "now": plan["name"],
                                               "ids": plan["ids"]})

        await _mutate_and_reload(hass, entry, f"brought in {len(chosen)} device(s)", _add)
    return outcome


# -------------------------------------------------------------------- the commands

def _fail(connection, msg, err):
    connection.send_error(msg["id"], "virtual_bring_in", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): WS_PREVIEW,
    vol.Required("upload_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_preview(hass: HomeAssistant, connection, msg) -> None:
    """What each device in the file would do if brought in, compared with every group."""
    try:
        parsed = get_upload(hass, msg["upload_id"])
        index = Index(*await _all_groups(hass))
    except BringInError as err:
        return _fail(connection, msg, err)
    connection.send_result(msg["id"], {
        "status": await hass.async_add_executor_job(preview, parsed["devices"], index)})


@websocket_api.websocket_command({
    vol.Required("type"): WS_APPLY,
    vol.Required("upload_id"): str,
    vol.Optional("group"): vol.Any(str, None),
    vol.Optional("new_group"): vol.Any(str, None),
    vol.Required("keys"): [str],
    vol.Optional("renames", default=dict): RENAMES_SCHEMA,
})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_apply(hass: HomeAssistant, connection, msg) -> None:
    new_group = (msg.get("new_group") or "").strip()
    if not new_group and not msg.get("group"):
        return _fail(connection, msg, BringInError("Choose a group, or name a new one."))
    try:
        result = await async_apply(hass, msg["upload_id"], msg.get("group"), new_group,
                                   msg["keys"], msg["renames"])
    except (BringInError, HomeAssistantError, vol.Invalid) as err:
        return _fail(connection, msg, err)
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): WS_FORGET, vol.Required("upload_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_forget(hass: HomeAssistant, connection, msg) -> None:
    hass.data.get(_UPLOADS, {}).pop(msg["upload_id"], None)
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({
    vol.Required("type"): WS_EXPORT_REVIEW,
    vol.Optional("exclude_integrations"): [str],
    vol.Optional("exclude_entities"): [str],
    vol.Optional("exclude_devices"): [str],
})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_export_review(hass: HomeAssistant, connection, msg) -> None:
    """Every name an export with these filters would contain, to be reviewed before
    it is written. Reads only."""
    from .export import EXPORT_SCHEMA, _collect, load_platform_schemas
    data = EXPORT_SCHEMA({k: v for k, v in msg.items() if k not in ("id", "type")})
    schemas = await hass.async_add_executor_job(load_platform_schemas)
    devices, _skipped = _collect(hass, data, schemas)
    connection.send_result(msg["id"], {"devices": summarise(devices)})


def async_register_bring_in(hass: HomeAssistant) -> None:
    for command in (_ws_preview, _ws_apply, _ws_forget, _ws_export_review):
        websocket_api.async_register_command(hass, command)
    hass.http.register_view(ImportUploadView())
