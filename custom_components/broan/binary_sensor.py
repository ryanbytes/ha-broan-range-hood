"""Binary sensor entities for Broan Range Hood."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONNECTION_STATUS_CONNECTED,
    DOMAIN,
    SHADOW_CONNECTION_STATUS,
)
from .coordinator import BroanCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BroanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BroanConnectivitySensor(coordinator, entry)])


class BroanConnectivitySensor(CoordinatorEntity[BroanCoordinator], BinarySensorEntity):
    """Reports whether the range hood is reachable on the cloud."""

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: BroanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_uid)},
            name=coordinator.device_name,
            manufacturer="Broan-NuTone",
            model=coordinator.device_uid,
            # sw_version filled in by sensor once FW is known
        )

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.get_shadow_value(
            SHADOW_CONNECTION_STATUS, as_int=True
        )
        if status is None:
            return None
        return status == CONNECTION_STATUS_CONNECTED
