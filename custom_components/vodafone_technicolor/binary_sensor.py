from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from .entity import VodafoneEntity
from .sensor import NETWORK_NAMES


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    entities = [VodafoneInternetSensor(c), VodafoneBusySensor(c)]
    entities += [VodafoneWifiEnabledSensor(c, key) for key in ("wifi_24", "wifi_5", "guest")]
    async_add_entities(entities)


class VodafoneInternetSensor(VodafoneEntity, BinarySensorEntity):
    _attr_name = "Internet"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator):
        super().__init__(coordinator, "internet_connected")

    @property
    def is_on(self):
        return self.coordinator.data.router.get("internet") == "OPERATIONAL"


class VodafoneWifiEnabledSensor(VodafoneEntity, BinarySensorEntity):
    _attr_icon = "mdi:wifi-check"

    def __init__(self, coordinator, network):
        super().__init__(coordinator, f"{network}_enabled")
        self._network = network
        self._attr_name = f"{NETWORK_NAMES[network]} enabled"

    @property
    def is_on(self):
        return self.coordinator.data.networks.get(self._network, {}).get("enabled")


class VodafoneBusySensor(VodafoneEntity, BinarySensorEntity):
    """On while someone else is logged in to the web interface (values are then from the last successful read)."""

    _attr_name = "Web interface in use"
    _attr_icon = "mdi:account-lock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, "web_interface_in_use")

    @property
    def is_on(self):
        return self.coordinator.busy
