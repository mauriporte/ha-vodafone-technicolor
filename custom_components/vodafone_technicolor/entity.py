from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, VodafoneCoordinator


class VodafoneEntity(CoordinatorEntity[VodafoneCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: VodafoneCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        router = coordinator.data.router
        mac = router.get("lan_mac")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            connections={(CONNECTION_NETWORK_MAC, mac.lower())} if mac else set(),
            name="Vodafone Station",
            manufacturer="Technicolor / Vodafone",
            sw_version=router.get("firmware"),
            hw_version=router.get("hardware"),
            configuration_url=f"http://{entry.data['host']}",
        )
