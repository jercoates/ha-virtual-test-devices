"""
Virtual air quality sensor.

Home Assistant's air quality entity is read-only: nothing can command it, it only
reports. So this one is driven with `virtual.set_air_quality`, which sets any of the
readings it carries. A reading the original device never reported is never shown (an
absent reading is not zero), so `readings` names the ones this device has.

The entity's own state is its fine-particle (PM2.5) reading, which is how Home
Assistant defines it, so PM2.5 is always one of the readings.
"""

import logging
import math
import voluptuous as vol
from collections.abc import Callable

import homeassistant.helpers.config_validation as cv
from homeassistant.components.air_quality import (
    DOMAIN as PLATFORM_DOMAIN,
    AirQualityEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import get_entity_configs, get_entity_from_domain
from .const import *
from .entity import VirtualEntity, virtual_schema


_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = [COMPONENT_DOMAIN]

DEFAULT_AIR_QUALITY_VALUE = "0"

CONF_READINGS = "readings"

READINGS = AIR_QUALITY_READINGS

# What a new test device reports when nothing says otherwise.
DEFAULT_READINGS = ["particulate_matter_2_5", "particulate_matter_10", "air_quality_index"]

BASE_SCHEMA = virtual_schema(DEFAULT_AIR_QUALITY_VALUE, {
    vol.Optional(CONF_READINGS): vol.All(cv.ensure_list, [vol.In(READINGS)]),
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(BASE_SCHEMA)
AIR_QUALITY_SCHEMA = vol.Schema(BASE_SCHEMA)



def _reading_value(value):
    """A reading is a real number: NaN and infinity are refused, not shown."""
    number = float(value)
    if not math.isfinite(number):
        raise vol.Invalid("a reading must be a finite number")
    return number


SERVICE_SET_AIR_QUALITY = "set_air_quality"
SET_AIR_QUALITY_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    **{vol.Optional(name): _reading_value for name in READINGS},
})


def setup_services(hass: HomeAssistant) -> None:
    async def _set_air_quality(call):
        values = {k: v for k, v in call.data.items() if k in READINGS}
        for entity_id in call.data[ATTR_ENTITY_ID]:
            get_entity_from_domain(hass, PLATFORM_DOMAIN, entity_id).set_readings(values)

    if not hass.services.has_service(COMPONENT_DOMAIN, SERVICE_SET_AIR_QUALITY):
        hass.services.async_register(
            COMPONENT_DOMAIN, SERVICE_SET_AIR_QUALITY, _set_air_quality,
            schema=SET_AIR_QUALITY_SCHEMA)


async def async_setup_platform(
        hass: HomeAssistant, config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        _discovery_info: DiscoveryInfoType | None = None) -> None:
    if hass.data[COMPONENT_CONFIG].get(CONF_YAML_CONFIG, False):
        async_add_entities([VirtualAirQuality(config, True)], True)
        setup_services(hass)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry,
        async_add_entities: Callable[[list], None]) -> None:
    entities = []
    for entity in get_entity_configs(hass, entry.data[ATTR_GROUP_NAME], PLATFORM_DOMAIN):
        entities.append(VirtualAirQuality(AIR_QUALITY_SCHEMA(entity), False))
    async_add_entities(entities)
    setup_services(hass)


def _reading(name):
    """The base class reads each of these as a property; ours answers from what the
    device was set to, and None (not shown) for one it does not carry."""
    return property(lambda self: self._values.get(name))


class VirtualAirQuality(VirtualEntity, AirQualityEntity):
    """Representation of a Virtual air quality sensor."""

    particulate_matter_2_5 = _reading("particulate_matter_2_5")
    particulate_matter_10 = _reading("particulate_matter_10")
    particulate_matter_0_1 = _reading("particulate_matter_0_1")
    air_quality_index = _reading("air_quality_index")
    ozone = _reading("ozone")
    carbon_monoxide = _reading("carbon_monoxide")
    carbon_dioxide = _reading("carbon_dioxide")
    sulphur_dioxide = _reading("sulphur_dioxide")
    nitrogen_oxide = _reading("nitrogen_oxide")
    nitrogen_monoxide = _reading("nitrogen_monoxide")
    nitrogen_dioxide = _reading("nitrogen_dioxide")

    def __init__(self, config, old_style: bool):
        super().__init__(config, PLATFORM_DOMAIN, old_style)

        # PM2.5 is the entity's state, so it is always carried.
        carried = list(config.get(CONF_READINGS) or DEFAULT_READINGS)
        if "particulate_matter_2_5" not in carried:
            carried.insert(0, "particulate_matter_2_5")
        self._carried = carried
        self._values = {}

        _LOGGER.info(f"VirtualAirQuality: {self.name} created")

    def _create_state(self, config):
        super()._create_state(config)
        try:
            start = _reading_value(config.get(CONF_INITIAL_VALUE, DEFAULT_AIR_QUALITY_VALUE))
        except (TypeError, ValueError, vol.Invalid):
            start = 0.0
        self._values = {name: start for name in self._carried}

    def _restore_state(self, state, config):
        super()._restore_state(state, config)
        # A reading that was not stored (the sensor was unavailable or unknown when
        # Home Assistant stopped) stays unknown: zero is a real reading, not "none".
        self._values = {}
        for name in self._carried:
            value = state.attributes.get(name)
            if name == "particulate_matter_2_5" and value is None:
                value = state.state
            try:
                self._values[name] = _reading_value(value)
            except (TypeError, ValueError, vol.Invalid):
                pass

    def set_readings(self, values: dict) -> None:
        """Set readings. One this device does not carry is refused, not invented:
        a device that never reported ozone must not start reporting it."""
        unknown = sorted(set(values) - set(self._carried))
        if unknown:
            raise ServiceValidationError(
                f"{self.entity_id} does not carry {', '.join(unknown)}; "
                f"it carries {', '.join(self._carried)}")
        self._values.update(values)
        self.async_schedule_update_ha_state()
