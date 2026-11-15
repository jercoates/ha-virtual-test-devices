"""
Virtual lawn mower.

A settable lawn mower for testing. Driven with Home Assistant's own
`lawn_mower.start_mowing`, `pause`, `dock` and `stop` actions. Two states have no
action that reaches them (`error` and `returning`), and a piston about a stuck
mower needs `error`, so `virtual.set_lawn_mower_activity` sets any state directly.
"""

import logging
import voluptuous as vol
from collections.abc import Callable

import homeassistant.helpers.config_validation as cv
from homeassistant.components.lawn_mower import (
    DOMAIN as PLATFORM_DOMAIN,
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import get_entity_configs, get_entity_from_domain
from .const import *
from .entity import FEATURES_SCHEMA, VirtualEntity, feature_flags, virtual_schema


_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = [COMPONENT_DOMAIN]

DEFAULT_LAWN_MOWER_VALUE = "docked"

# What a new test mower can do. STOP only exists on newer Home Assistants, so it is
# looked up rather than named.
DEFAULT_FEATURES = (
    LawnMowerEntityFeature.START_MOWING
    | LawnMowerEntityFeature.PAUSE
    | LawnMowerEntityFeature.DOCK
    | getattr(LawnMowerEntityFeature, "STOP", LawnMowerEntityFeature(0))
)

BASE_SCHEMA = virtual_schema(DEFAULT_LAWN_MOWER_VALUE, {
    **FEATURES_SCHEMA,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(BASE_SCHEMA)
LAWN_MOWER_SCHEMA = vol.Schema(BASE_SCHEMA)

_STATES = {a.value: a for a in LawnMowerActivity}

SERVICE_SET_ACTIVITY = "set_lawn_mower_activity"
SET_ACTIVITY_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    vol.Required("activity"): vol.In(list(_STATES)),
})


def setup_services(hass: HomeAssistant) -> None:
    async def _set_activity(call):
        for entity_id in call.data[ATTR_ENTITY_ID]:
            get_entity_from_domain(hass, PLATFORM_DOMAIN, entity_id) \
                .set_activity(_STATES[call.data["activity"]])

    if not hass.services.has_service(COMPONENT_DOMAIN, SERVICE_SET_ACTIVITY):
        hass.services.async_register(
            COMPONENT_DOMAIN, SERVICE_SET_ACTIVITY, _set_activity,
            schema=SET_ACTIVITY_SCHEMA)


async def async_setup_platform(
        hass: HomeAssistant, config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        _discovery_info: DiscoveryInfoType | None = None) -> None:
    if hass.data[COMPONENT_CONFIG].get(CONF_YAML_CONFIG, False):
        async_add_entities([VirtualLawnMower(config, True)], True)
        setup_services(hass)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry,
        async_add_entities: Callable[[list], None]) -> None:
    entities = []
    for entity in get_entity_configs(hass, entry.data[ATTR_GROUP_NAME], PLATFORM_DOMAIN):
        entities.append(VirtualLawnMower(LAWN_MOWER_SCHEMA(entity), False))
    async_add_entities(entities)
    setup_services(hass)


class VirtualLawnMower(VirtualEntity, LawnMowerEntity):
    """Representation of a Virtual lawn mower."""

    def __init__(self, config, old_style: bool):
        super().__init__(config, PLATFORM_DOMAIN, old_style)

        self._attr_supported_features = feature_flags(
            config, LawnMowerEntityFeature, DEFAULT_FEATURES)

        _LOGGER.info(f"VirtualLawnMower: {self.name} created")

    def _create_state(self, config):
        super()._create_state(config)
        self._attr_activity = _STATES.get(
            config.get(CONF_INITIAL_VALUE, DEFAULT_LAWN_MOWER_VALUE).lower(),
            LawnMowerActivity.DOCKED)

    def _restore_state(self, state, config):
        super()._restore_state(state, config)
        self._attr_activity = _STATES.get(state.state, LawnMowerActivity.DOCKED)

    def set_activity(self, activity: LawnMowerActivity) -> None:
        self._attr_activity = activity
        self.async_write_ha_state()

    async def async_start_mowing(self) -> None:
        self.set_activity(LawnMowerActivity.MOWING)

    async def async_pause(self) -> None:
        self.set_activity(LawnMowerActivity.PAUSED)

    async def async_dock(self) -> None:
        self.set_activity(LawnMowerActivity.DOCKED)

    async def async_stop(self) -> None:
        self.set_activity(LawnMowerActivity.IDLE)
