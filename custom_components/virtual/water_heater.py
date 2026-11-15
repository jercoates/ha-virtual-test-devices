"""
Virtual water heater.

A settable water heater for testing. Driven with Home Assistant's own
`water_heater.set_temperature`, `set_operation_mode`, `set_away_mode` and
`turn_on` / `turn_off` actions. The CURRENT temperature has no action of its own
(a real heater reports it), so `virtual.set_current_temperature` sets it, the same
action a virtual thermostat uses.

The temperature unit is the clone's (limits arrive in whatever unit Home Assistant
reports them in, and declaring a different unit makes Home Assistant convert twice).
"""

import logging
import voluptuous as vol
from collections.abc import Callable
from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.components.water_heater import (
    DOMAIN as PLATFORM_DOMAIN,
    STATE_OFF,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.unit_conversion import TemperatureConverter

from . import get_entity_configs
# The thermostat already names these options and owns the shared current-temperature action.
from .climate import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_TARGET_TEMP_STEP,
    CONF_TEMPERATURE_UNIT,
    setup_services,
)
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

DEFAULT_WATER_HEATER_VALUE = "eco"  # initial operation mode

# Home Assistant 2026.11 renamed the temperature unit
# (`_attr_temperature_unit` -> `_attr_native_temperature_unit`) and warns about the
# old name; 2026.10 and earlier only know the old one. Use whichever the installed
# Home Assistant understands (the thermostat does the same).
_UNIT_ATTR = ("_attr_native_temperature_unit"
              if hasattr(WaterHeaterEntity, "native_temperature_unit")
              else "_attr_temperature_unit")
_CURRENT_ATTR = ("_attr_native_current_temperature"
                 if hasattr(WaterHeaterEntity, "native_current_temperature")
                 else "_attr_current_temperature")
_TARGET_ATTR = ("_attr_native_target_temperature"
                if hasattr(WaterHeaterEntity, "native_target_temperature")
                else "_attr_target_temperature")

CONF_OPERATION_LIST = "operation_list"

# What a new test water heater can do: a target, a mode menu, away mode and on/off.
DEFAULT_FEATURES = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE
    | WaterHeaterEntityFeature.OPERATION_MODE
    | WaterHeaterEntityFeature.AWAY_MODE
    | WaterHeaterEntityFeature.ON_OFF
)
DEFAULT_OPERATIONS = ["off", "eco", "electric", "performance"]
DEFAULT_MIN_C, DEFAULT_MAX_C = 30.0, 70.0

BASE_SCHEMA = virtual_schema(DEFAULT_WATER_HEATER_VALUE, {
    **FEATURES_SCHEMA,
    vol.Optional(CONF_OPERATION_LIST): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
    vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
    vol.Optional(CONF_TARGET_TEMP_STEP): vol.Coerce(float),
    vol.Optional(CONF_TEMPERATURE_UNIT): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(BASE_SCHEMA)
WATER_HEATER_SCHEMA = vol.Schema(BASE_SCHEMA)


async def async_setup_platform(
        hass: HomeAssistant, config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        _discovery_info: DiscoveryInfoType | None = None) -> None:
    if hass.data[COMPONENT_CONFIG].get(CONF_YAML_CONFIG, False):
        async_add_entities([VirtualWaterHeater(config, True)], True)
        setup_services(hass)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry,
        async_add_entities: Callable[[list], None]) -> None:
    entities = []
    for entity in get_entity_configs(hass, entry.data[ATTR_GROUP_NAME], PLATFORM_DOMAIN):
        entities.append(VirtualWaterHeater(WATER_HEATER_SCHEMA(entity), False))
    async_add_entities(entities)
    setup_services(hass)


class VirtualWaterHeater(VirtualEntity, WaterHeaterEntity):
    """Representation of a Virtual water heater."""

    def __init__(self, config, old_style: bool):
        super().__init__(config, PLATFORM_DOMAIN, old_style)

        setattr(self, _UNIT_ATTR, UnitOfTemperature.CELSIUS)
        self._attr_supported_features = feature_flags(
            config, WaterHeaterEntityFeature, DEFAULT_FEATURES)

        # A device that never named a mode menu has none: advertising one with
        # nothing in it offers a dropdown that errors when used.
        operations = optional_list(config, CONF_OPERATION_LIST)
        if operations is None and config.get(CONF_SUPPORTED_FEATURES) is None:
            operations = list(DEFAULT_OPERATIONS)
        self._attr_operation_list = operations
        if not operations:
            self._attr_supported_features &= ~WaterHeaterEntityFeature.OPERATION_MODE

        if (unit := config.get(CONF_TEMPERATURE_UNIT)) is not None:
            setattr(self, _UNIT_ATTR, (
                UnitOfTemperature.FAHRENHEIT if "F" in unit.upper()
                else UnitOfTemperature.CELSIUS))
        celsius = getattr(self, _UNIT_ATTR) == UnitOfTemperature.CELSIUS
        # Explicit limits: Home Assistant's own defaults are Fahrenheit numbers
        # (110 to 140) and would be converted a second time for a Celsius device.
        self._attr_min_temp = config.get(CONF_MIN_TEMP, DEFAULT_MIN_C if celsius else 90.0)
        self._attr_max_temp = config.get(CONF_MAX_TEMP, DEFAULT_MAX_C if celsius else 160.0)
        if (step := config.get(CONF_TARGET_TEMP_STEP)) is not None:
            self._attr_target_temperature_step = step

        self._last_on_operation = None
        _LOGGER.info(f"VirtualWaterHeater: {self.name} created")

    def _midpoint(self) -> float:
        """A starting target inside this heater's own limits."""
        celsius = getattr(self, _UNIT_ATTR) == UnitOfTemperature.CELSIUS
        default = 50.0 if celsius else 120.0
        low, high = self.min_temp, self.max_temp
        return default if low <= default <= high else round((low + high) / 2, 1)

    def _create_state(self, config):
        super()._create_state(config)
        wanted = config.get(CONF_INITIAL_VALUE, DEFAULT_WATER_HEATER_VALUE).lower()
        operations = self._attr_operation_list or []
        if operations:
            self._attr_current_operation = (
                wanted if wanted in operations else operations[0])
        mid = self._midpoint()
        setattr(self, _TARGET_ATTR, mid)
        setattr(self, _CURRENT_ATTR, mid - 5)
        if self._attr_supported_features & WaterHeaterEntityFeature.AWAY_MODE:
            self._attr_is_away_mode_on = False

    def _restore_state(self, state, config):
        super()._restore_state(state, config)
        attrs = state.attributes
        mid = self._midpoint()
        operations = self._attr_operation_list or []
        if operations:
            self._attr_current_operation = (
                state.state if state.state in operations else operations[0])
        setattr(self, _TARGET_ATTR, self._to_native(attrs.get(ATTR_TEMPERATURE), mid))
        setattr(self, _CURRENT_ATTR, self._to_native(attrs.get("current_temperature"), mid - 5))
        if self._attr_supported_features & WaterHeaterEntityFeature.AWAY_MODE:
            self._attr_is_away_mode_on = attrs.get("away_mode") == "on"

    def _to_native(self, value, fallback: float) -> float:
        """A temperature Home Assistant published, in the unit the heater keeps. The
        stored state is in Home Assistant's own unit, so a heater declared in the
        other unit would read back wrong after a restart without this."""
        if value is None:
            return fallback
        try:
            return TemperatureConverter.convert(
                float(value), self.hass.config.units.temperature_unit,
                getattr(self, _UNIT_ATTR))
        except (TypeError, ValueError):
            return fallback

    async def async_set_temperature(self, **kwargs: Any) -> None:
        # Home Assistant's own action also takes an operation mode with the target.
        if (value := kwargs.get(ATTR_TEMPERATURE)) is not None:
            setattr(self, _TARGET_ATTR, value)
        mode = kwargs.get("operation_mode")
        if mode is not None and mode in (self._attr_operation_list or []):
            await self.async_set_operation_mode(mode)    # one write, with both changes
        else:
            self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        self._attr_current_operation = operation_mode
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        operations = self._attr_operation_list or []
        if self._attr_current_operation == STATE_OFF and operations:
            back = self._last_on_operation
            self._attr_current_operation = back if back in operations else next(
                (o for o in operations if o != STATE_OFF), operations[0])
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._attr_current_operation != STATE_OFF:
            self._last_on_operation = self._attr_current_operation
        if STATE_OFF in (self._attr_operation_list or []):
            self._attr_current_operation = STATE_OFF
        self.async_write_ha_state()

    async def async_turn_away_mode_on(self) -> None:
        self._attr_is_away_mode_on = True
        self.async_write_ha_state()

    async def async_turn_away_mode_off(self) -> None:
        self._attr_is_away_mode_on = False
        self.async_write_ha_state()

    def set_current_temperature(self, value: float) -> None:
        """Set the reported current temperature (for tests), in this heater's own unit."""
        _LOGGER.debug(f"{self.name} current_temperature -> {value}")
        setattr(self, _CURRENT_ATTR, float(value))
        self.async_schedule_update_ha_state()
