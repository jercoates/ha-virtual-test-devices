from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, MANUFACTURER, AREA_NAME

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([VirtualMediaPlayer()])

class VirtualMediaPlayer(MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self):
        self._attr_unique_id = f"{DOMAIN}_media_player"
        self._attr_name = "Virtual Media Player"
        self._attr_state = MediaPlayerState.IDLE

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "media_player")},
            name="Virtual Media Player",
            manufacturer=MANUFACTURER,
            model="Virtual Test",
            suggested_area=AREA_NAME,
        )