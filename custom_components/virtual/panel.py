"""The sidebar panel, and the admin-only commands it talks to.

Registered ONCE per Home Assistant (from `async_setup`, which runs once per
process), never per group: a second registration of the same panel path raises,
and so would a second static path. It also must not depend on `hass.data[virtual]`,
which loses a group for a moment on every reload; the groups listed here are read
from the config entries, which are always there.

The panel is an admin tool. Each of the four `virtual/...` commands here checks
for an admin (the panel being hidden from other users is not a check: its script
file is an ordinary static file), and none returns a group's raw entity configs,
which can carry lock and alarm codes and text defaults. The actions the panel
calls (create, clone, remove, describe, export) are admin services too, see where
each is registered.
"""

import json
import logging
import pathlib

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er

from . import __version__
from .bring_in import async_register_bring_in
from .clone import REPRODUCIBLE_DOMAINS
from .const import ATTR_GROUP_NAME, COMPONENT_DOMAIN
from .export import DEFAULT_EXCLUDE_INTEGRATIONS

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "virtual-devices"
PANEL_ELEMENT = "virtual-test-devices-panel"
STATIC_URL = "/virtual_static"
SCRIPT_NAME = "virtual-panel.js"

WS_GROUPS = "virtual/groups"
WS_DEVICES = "virtual/devices"
WS_TEMPLATES = "virtual/templates"
WS_CLONABLE = "virtual/clonable"

TEMPLATES_FILE = "templates.json"


def read_templates() -> list:
    """The kinds of test device the panel offers to create, from `templates.json`
    beside this file. It is DATA, not code: what a "Motion sensor" is made of can
    be changed by editing that file, and nothing here has to know. Blocking I/O,
    so it runs in the executor."""
    path = pathlib.Path(__file__).with_name(TEMPLATES_FILE)
    return json.loads(path.read_text(encoding="utf-8"))


def clonable_summary(hass: HomeAssistant) -> list:
    """The real devices that could be cloned: those with at least one entity this
    integration can reproduce. Not the test devices themselves, and not the
    integrations an export also leaves out (a test Home Assistant has its own).
    A name and a short description of what is in it, nothing else."""
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
    skipped = set(DEFAULT_EXCLUDE_INTEGRATIONS)
    found = []
    for device in dev_reg.devices.values():
        if device.disabled_by or any(
                ident[0] == COMPONENT_DOMAIN for ident in device.identifiers):
            continue
        rows = [row for row in er.async_entries_for_device(ent_reg, device.id)
                if row.domain in REPRODUCIBLE_DOMAINS and row.platform not in skipped]
        if not rows:
            continue
        found.append({
            "device_id": device.id,
            "name": device.name_by_user or device.name or "Device",
            "kind": " ".join(part for part in (device.manufacturer, device.model) if part),
            "domains": sorted({row.domain for row in rows}),
            "entities": len(rows),
        })
    return sorted(found, key=lambda d: str(d["name"]).lower())


def groups_summary(hass: HomeAssistant) -> list:
    """What the panel may know about each group: its name and whether it is
    running. Not its file, and nothing from inside the file."""
    return [{
        "name": entry.data.get(ATTR_GROUP_NAME),
        "state": getattr(entry.state, "value", str(entry.state)),
    } for entry in hass.config_entries.async_entries(COMPONENT_DOMAIN)]


def devices_summary(hass: HomeAssistant) -> list:
    """The devices every group owns and the entities under each, by registry id.

    Structure only. The panel reads each entity's live state from Home Assistant
    itself (so it updates as things change, with nothing polled here), and nothing
    from a group's own config is included. `key` is the name the group's file
    files the device under, which is what removing it has to be given; `name` is
    what to show."""
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
    devices = {}
    for entry in hass.config_entries.async_entries(COMPONENT_DOMAIN):
        group = entry.data.get(ATTR_GROUP_NAME)
        for row in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if row.disabled_by:
                continue
            device = dev_reg.async_get(row.device_id) if row.device_id else None
            ident = row.device_id or row.entity_id
            item = devices.setdefault((entry.entry_id, ident), {
                "group": group,
                "name": ((device.name_by_user or device.name) if device else None)
                        or row.name or row.original_name or row.entity_id,
                "key": next((i[1] for i in (device.identifiers if device else ())
                             if i[0] == COMPONENT_DOMAIN), None),
                "entities": [],
            })
            item["entities"].append({
                "entity_id": row.entity_id,
                "domain": row.entity_id.split(".", 1)[0],
                "name": row.name or row.original_name or row.entity_id,
            })
    return sorted(devices.values(),
                  key=lambda d: (str(d["group"]).lower(), str(d["name"]).lower()))


@websocket_api.websocket_command({vol.Required("type"): WS_TEMPLATES})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_templates(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {
        "templates": await hass.async_add_executor_job(read_templates)})


@websocket_api.websocket_command({vol.Required("type"): WS_CLONABLE})
@websocket_api.require_admin
@callback
def _ws_clonable(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {"devices": clonable_summary(hass)})


@websocket_api.websocket_command({vol.Required("type"): WS_DEVICES})
@websocket_api.require_admin
@callback
def _ws_devices(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {"devices": devices_summary(hass)})


@websocket_api.websocket_command({vol.Required("type"): WS_GROUPS})
@websocket_api.require_admin
@callback
def _ws_groups(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {
        "version": __version__,
        "groups": groups_summary(hass),
    })


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the commands, serve the script and add the sidebar entry. Safe to
    call twice."""
    if frontend.async_panel_exists(hass, PANEL_URL_PATH):
        return

    websocket_api.async_register_command(hass, _ws_groups)
    websocket_api.async_register_command(hass, _ws_devices)
    websocket_api.async_register_command(hass, _ws_templates)
    websocket_api.async_register_command(hass, _ws_clonable)
    async_register_bring_in(hass)

    script = pathlib.Path(__file__).with_name("frontend") / SCRIPT_NAME
    # No cache header: the file is small, and a long-lived cached copy would keep
    # showing the old panel after an upgrade.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"{STATIC_URL}/{SCRIPT_NAME}", str(script), False)])

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="Test Devices",
        sidebar_icon="mdi:test-tube",
        module_url=f"{STATIC_URL}/{SCRIPT_NAME}?v={__version__}",
        require_admin=True,
    )
    _LOGGER.debug("virtual: registered the %s panel", PANEL_URL_PATH)
