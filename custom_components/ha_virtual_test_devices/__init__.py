from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN, AREA_NAME, MANUFACTURER

PLATFORMS = ["binary_sensor", "sensor", "switch", "light", "lock", "media_player"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Virtual Test Devices."""
    hass.data.setdefault(DOMAIN, {})

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration and clean up devices."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        device_registry = dr.async_get(hass)
        for device in list(device_registry.devices.values()):
            if entry.entry_id in device.config_entries:
                device_registry.async_remove_device(device.id)

    return unload_ok