from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, MANUFACTURER, AREA_NAME

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([VirtualLock()])

class VirtualLock(LockEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self):
        self._attr_unique_id = f"{DOMAIN}_lock"
        self._attr_name = "Virtual Lock"
        self._attr_is_locked = True

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "lock")},
            name="Virtual Lock",
            manufacturer=MANUFACTURER,
            model="Virtual Test",
            suggested_area=AREA_NAME,
        )

    async def async_lock(self, **kwargs):
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs):
        self._attr_is_locked = False
        self.async_write_ha_state()