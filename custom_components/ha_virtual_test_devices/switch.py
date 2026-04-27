from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, MANUFACTURER, AREA_NAME

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([VirtualSwitch()])

class VirtualSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self):
        self._attr_unique_id = f"{DOMAIN}_switch"
        self._attr_name = "Virtual Switch"
        self._attr_is_on = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "switch")},
            name="Virtual Switch",
            manufacturer=MANUFACTURER,
            model="Virtual Test",
            suggested_area=AREA_NAME,
        )

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()