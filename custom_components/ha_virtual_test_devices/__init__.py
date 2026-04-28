from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.components import persistent_notification
from .const import DOMAIN, AREA_NAME, MANUFACTURER

PLATFORMS = ["binary_sensor", "sensor", "switch", "light", "lock", "media_player"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Virtual Test Devices."""
    hass.data.setdefault(DOMAIN, {})

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create helpful notification for first-time users
    await persistent_notification.async_create(
        hass,
        title="HA Virtual Test Devices",
        message=(
            "Virtual devices have been created in the **Test** area.\n\n"
            "For the best testing experience, import the **Virtual Test Lab** dashboard:\n\n"
            "1. Go to **Settings → Dashboards**\n"
            "2. Click the three dots (top right) → **Import dashboard**\n"
            "3. Paste the content from `test_dashboard.yaml` in the repository.\n\n"
            "This gives you big buttons to easily trigger smoke, water, motion, etc."
        ),
        notification_id="virtual_test_devices_setup",
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up devices
        device_registry = dr.async_get(hass)
        for device in list(device_registry.devices.values()):
            if entry.entry_id in device.config_entries:
                device_registry.async_remove_device(device.id)

        # Remove notification
        persistent_notification.async_dismiss(hass, "virtual_test_devices_setup")

    return unload_ok
