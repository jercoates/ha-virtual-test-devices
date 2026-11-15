"""
Virtual remote (a universal remote or an IR/RF blaster).

A settable remote for testing. On/off and the current activity are driven with
Home Assistant's own `remote.turn_on` (with an `activity`) and `remote.turn_off`.

`remote.send_command`, `learn_command` and `delete_command` reach nothing real, so
each one is RECORDED instead of ignored, the way the lock records the code it was
sent: `last_action`, `last_command`, `last_device` and a `sequence` that counts every
call. A piston or a test can then see that the call arrived and with what, and the
counter changing is a state change, so an automation watching it triggers.
"""

import logging
import voluptuous as vol
from collections.abc import Callable, Iterable
from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.components.remote import (
    DOMAIN as PLATFORM_DOMAIN,
    RemoteEntity,
    RemoteEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import get_entity_configs
from .const import *
from .entity import (
    FEATURES_SCHEMA,
    VirtualEntity,
    feature_flags,
    optional_list,
    virtual_schema,
)


_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = [COMPONENT_DOMAIN]

DEFAULT_REMOTE_VALUE = "off"

CONF_ACTIVITY_LIST = "activity_list"

# What a new test remote can do. Activities need a list to pick from, so the
# ACTIVITY bit is added only when one is given.
DEFAULT_FEATURES = (
    RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND
)

BASE_SCHEMA = virtual_schema(DEFAULT_REMOTE_VALUE, {
    **FEATURES_SCHEMA,
    vol.Optional(CONF_ACTIVITY_LIST): vol.All(cv.ensure_list, [cv.string]),
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(BASE_SCHEMA)
REMOTE_SCHEMA = vol.Schema(BASE_SCHEMA)


async def async_setup_platform(
        hass: HomeAssistant, config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        _discovery_info: DiscoveryInfoType | None = None) -> None:
    if hass.data[COMPONENT_CONFIG].get(CONF_YAML_CONFIG, False):
        async_add_entities([VirtualRemote(config, True)], True)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry,
        async_add_entities: Callable[[list], None]) -> None:
    entities = []
    for entity in get_entity_configs(hass, entry.data[ATTR_GROUP_NAME], PLATFORM_DOMAIN):
        entities.append(VirtualRemote(REMOTE_SCHEMA(entity), False))
    async_add_entities(entities)


class VirtualRemote(VirtualEntity, RemoteEntity):
    """Representation of a Virtual remote."""

    def __init__(self, config, old_style: bool):
        super().__init__(config, PLATFORM_DOMAIN, old_style)

        self._attr_supported_features = feature_flags(
            config, RemoteEntityFeature, DEFAULT_FEATURES)
        self._attr_activity_list = optional_list(config, CONF_ACTIVITY_LIST)
        if self._attr_activity_list:
            if config.get(CONF_SUPPORTED_FEATURES) is None:
                self._attr_supported_features |= RemoteEntityFeature.ACTIVITY
        else:
            # An activity feature with no activities offers an empty dropdown.
            self._attr_supported_features &= ~RemoteEntityFeature.ACTIVITY

        self._reset_record()
        _LOGGER.info(f"VirtualRemote: {self.name} created")

    def _reset_record(self) -> None:
        self._last_action = None
        self._last_command = None
        self._last_device = None
        self._sequence = 0

    def _create_state(self, config):
        super()._create_state(config)
        self._attr_is_on = config.get(CONF_INITIAL_VALUE, DEFAULT_REMOTE_VALUE).lower() == STATE_ON
        self._attr_current_activity = None
        self._reset_record()

    def _restore_state(self, state, config):
        super()._restore_state(state, config)
        self._attr_is_on = state.state.lower() == STATE_ON
        activity = state.attributes.get("current_activity")
        self._attr_current_activity = (
            activity if activity in (self._attr_activity_list or []) else None)
        self._reset_record()

    def _update_attributes(self):
        super()._update_attributes()
        self._attr_extra_state_attributes["last_action"] = self._last_action
        self._attr_extra_state_attributes["last_command"] = self._last_command
        self._attr_extra_state_attributes["last_device"] = self._last_device
        self._attr_extra_state_attributes["sequence"] = self._sequence

    def _record(self, action: str, command=None, device=None) -> None:
        self._last_action = action
        self._last_command = command
        self._last_device = device
        self._sequence += 1
        self._update_attributes()
        self.async_write_ha_state()

    async def async_turn_on(self, activity: str | None = None, **kwargs: Any) -> None:
        self._attr_is_on = True
        if activity and activity in (self._attr_activity_list or []):
            self._attr_current_activity = activity
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self._attr_current_activity = None
        self.async_write_ha_state()

    @staticmethod
    def _one(value) -> str | None:
        """`device` and `command` arrive as a list when sent through the action
        UI and as a plain string from a script; the record shows both the same way."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, Iterable):
            return ", ".join(str(v) for v in value)
        return str(value)

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        _LOGGER.info(f"{self.name} send_command {command} {kwargs}")
        self._record("send_command", self._one(command), self._one(kwargs.get("device")))

    async def async_learn_command(self, **kwargs: Any) -> None:
        _LOGGER.info(f"{self.name} learn_command {kwargs}")
        self._record("learn_command", self._one(kwargs.get("command")),
                     self._one(kwargs.get("device")))

    async def async_delete_command(self, **kwargs: Any) -> None:
        _LOGGER.info(f"{self.name} delete_command {kwargs}")
        self._record("delete_command", self._one(kwargs.get("command")),
                     self._one(kwargs.get("device")))
