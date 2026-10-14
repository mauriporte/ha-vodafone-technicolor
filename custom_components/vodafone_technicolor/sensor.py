from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.util import dt as dt_util

from .entity import VodafoneEntity

ROUTER_SENSORS = {
    # key: (name, icon, diagnostic)
    "public_ip": ("Public IP", "mdi:earth", False),
    "lan_ip": ("LAN IP", "mdi:ip-network", True),
    "lan_mac": ("MAC", "mdi:network-outline", True),
    "firmware": ("Firmware", "mdi:chip", True),
    "internet": ("Internet status", "mdi:web", False),
}
NETWORK_NAMES = {"wifi_24": "WiFi 2.4 GHz", "wifi_5": "WiFi 5 GHz", "guest": "Guest WiFi", "wired": "Wired"}


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    entities = [VodafoneRouterSensor(c, k, *v) for k, v in ROUTER_SENSORS.items()]
    entities += [VodafoneUptimeSensor(c), VodafoneCpuSensor(c), VodafoneMemorySensor(c), VodafoneCableSensor(c)]
    entities += [VodafoneClientsSensor(c, key) for key in NETWORK_NAMES]
    entities += [VodafonePhoneSensor(c, n) for n in c.data.phones]
    async_add_entities(entities)


class VodafoneRouterSensor(VodafoneEntity, SensorEntity):
    def __init__(self, coordinator, key, name, icon, diagnostic):
        super().__init__(coordinator, key)
        self._key = key
        self._attr_name, self._attr_icon = name, icon
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return self.coordinator.data.router.get(self._key)

    @property
    def extra_state_attributes(self):
        if self._key == "public_ip":
            return {"dns": self.coordinator.data.router.get("dns")}
        if self._key == "lan_ip":
            return {"ports": self.coordinator.data.router.get("ports")}
        return None


class VodafoneUptimeSensor(VodafoneEntity, SensorEntity):
    _attr_name = "Last boot"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, "last_boot")
        self._boot = None

    @property
    def native_value(self):
        secs = self.coordinator.data.router.get("uptime")
        if secs is None:
            return None
        boot = (dt_util.utcnow() - timedelta(seconds=secs)).replace(microsecond=0)
        # Polling delay shifts the computed boot time by a few seconds: only move it on a real reboot.
        if self._boot is None or abs((boot - self._boot).total_seconds()) > 120:
            self._boot = boot
        return self._boot


class VodafoneCpuSensor(VodafoneEntity, SensorEntity):
    _attr_name = "CPU usage"
    _attr_icon = "mdi:cpu-64-bit"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, "cpu")

    @property
    def native_value(self):
        return self.coordinator.data.router.get("cpu")


class VodafoneMemorySensor(VodafoneEntity, SensorEntity):
    _attr_name = "Memory used"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.KILOBYTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, "memory_used")

    @property
    def native_value(self):
        return self.coordinator.data.router.get("memory_used_kb")


class VodafoneCableSensor(VodafoneEntity, SensorEntity):
    """Cable (DOCSIS) line: state = operational status, attributes = channel summary."""

    _attr_name = "Cable line"
    _attr_icon = "mdi:cable-data"

    def __init__(self, coordinator):
        super().__init__(coordinator, "cable_line")

    @property
    def native_value(self):
        return self.coordinator.data.docsis.get("status")

    @property
    def extra_state_attributes(self):
        return {k: v for k, v in self.coordinator.data.docsis.items() if k != "status"}


class VodafoneClientsSensor(VodafoneEntity, SensorEntity):
    """State = number of active devices on this network; attributes = the device list."""

    _attr_native_unit_of_measurement = "devices"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, network):
        super().__init__(coordinator, f"clients_{network}")
        self._network = network
        self._attr_name = f"{NETWORK_NAMES[network]} devices"
        self._attr_icon = "mdi:ethernet" if network == "wired" else "mdi:wifi"

    def _clients(self):
        return [c for c in self.coordinator.data.clients if c["network"] == self._network]

    @property
    def native_value(self):
        return len(self._clients())

    @property
    def extra_state_attributes(self):
        net = self.coordinator.data.networks.get(self._network, {})
        return {
            "ssid": net.get("ssid"),
            "enabled": net.get("enabled"),
            "channel": net.get("channel"),
            "bandwidth": net.get("bandwidth"),
            "web_interface_in_use": self.coordinator.busy,
            "devices": [
                {k: c[k] for k in ("name", "ip", "mac", "signal", "link_mbps", "port", "connected_s", "type")}
                for c in sorted(self._clients(), key=lambda c: (c["name"] or "~").lower())
            ],
        }


class VodafonePhoneSensor(VodafoneEntity, SensorEntity):
    _attr_icon = "mdi:phone-classic"

    def __init__(self, coordinator, line):
        super().__init__(coordinator, f"phone_line_{line}")
        self._line = line
        self._attr_name = f"Phone line {line}"

    @property
    def native_value(self):
        return (self.coordinator.data.phones.get(self._line) or {}).get("status")
