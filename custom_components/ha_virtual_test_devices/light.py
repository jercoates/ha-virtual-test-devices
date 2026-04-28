from homeassistant.components.light import (
    LightEntity,
    ColorMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, MANUFACTURER, AREA_NAME

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([VirtualDimmableLight()])

class VirtualDimmableLight(LightEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = 0   # brightness only

    def __init__(self):
        self._attr_unique_id = f"{DOMAIN}_dimmable_light"
        self._attr_name = "Virtual Dimmable Light"
        self._attr_is_on = False
        self._attr_brightness = 255   # full brightness

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "dimmable_light")},
            name="Virtual Dimmable Light",
            manufacturer=MANUFACTURER,
            model="Virtual Test",
            suggested_area=AREA_NAME,
        )

    @property
    def is_on(self):
        return self._attr_is_on

    async def async_turn_on(self, brightness=None, **kwargs):
        self._attr_is_on = True
        if brightness is not None:
            self._attr_brightness = int(brightness)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()