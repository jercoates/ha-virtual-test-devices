from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfIlluminance
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, MANUFACTURER, AREA_NAME

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = [
        VirtualSensor("temp_sensor", "Virtual Temperature Sensor", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 22.0),
        VirtualSensor("humidity_sensor", "Virtual Humidity Sensor", SensorDeviceClass.HUMIDITY, "%", 45.0),
        VirtualSensor("lux_sensor", "Virtual Lux Sensor", SensorDeviceClass.ILLUMINANCE, UnitOfIlluminance.LUX, 300.0),
    ]
    async_add_entities(entities)

class VirtualSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, unique_id: str, name: str, device_class: str, unit: str, initial_value: float):
        self._attr_unique_id = f"{DOMAIN}_{unique_id}"
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_native_value = initial_value

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model="Virtual Test",
            suggested_area=AREA_NAME,
        )