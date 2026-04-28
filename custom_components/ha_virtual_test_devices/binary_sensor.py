from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, MANUFACTURER, AREA_NAME

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = [
        VirtualBinarySensor("motion_sensor", "Virtual Motion Sensor", BinarySensorDeviceClass.MOTION, "Motion", "Clear"),
        VirtualBinarySensor("door_sensor", "Virtual Door Sensor", BinarySensorDeviceClass.DOOR, "Open", "Closed"),
        VirtualBinarySensor("smoke_detector", "Virtual Smoke Detector", BinarySensorDeviceClass.SMOKE, "Smoke", "Clear"),
        VirtualBinarySensor("water_sensor", "Virtual Water Leak Sensor", BinarySensorDeviceClass.MOISTURE, "Leak", "Dry"),
        VirtualBinarySensor("co_detector", "Virtual CO Detector", BinarySensorDeviceClass.CO, "Detected", "Clear"),
    ]
    async_add_entities(entities)

class VirtualBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, unique_id: str, name: str, device_class: str, on_label: str = None, off_label: str = None):
        self._attr_unique_id = f"{DOMAIN}_{unique_id}"
        self._attr_name = name
        self._attr_device_class = device_class
        self._on_label = on_label
        self._off_label = off_label
        self._attr_is_on = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model="Virtual Test",
            suggested_area=AREA_NAME,
        )

    @property
    def is_on(self):
        return self._attr_is_on

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs):
        self._attr_is_on = not self._attr_is_on
        self.async_write_ha_state()