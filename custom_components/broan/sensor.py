"""Sensor entities for Broan Range Hood."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    FAN_AUTO_STATUS_NAMES,
    SHADOW_FAN_AUTO_STATUS,
    SHADOW_FW_ESP,
    SHADOW_FW_MAIN,
    SHADOW_FW_UI,
    SHADOW_OTA_AVAILABLE,
    SHADOW_WIFI_SSID,
)
from .coordinator import BroanCoordinator


@dataclass(frozen=True)
class BroanSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with Broan shadow-field metadata."""
    shadow_field: str = ""
    as_int: bool = False
    value_map: dict | None = field(default=None, compare=False)


SENSOR_DESCRIPTIONS: list[BroanSensorDescription] = [
    BroanSensorDescription(
        key="auto_op_status",
        name="Auto Operation Status",
        icon="mdi:robot",
        shadow_field=SHADOW_FAN_AUTO_STATUS,
        as_int=True,
        value_map=FAN_AUTO_STATUS_NAMES,
    ),
    BroanSensorDescription(
        key="wifi_ssid",
        name="Wi-Fi Network",
        icon="mdi:wifi",
        shadow_field=SHADOW_WIFI_SSID,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BroanSensorDescription(
        key="fw_esp",
        name="Firmware ESP",
        icon="mdi:chip",
        shadow_field=SHADOW_FW_ESP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BroanSensorDescription(
        key="fw_main",
        name="Firmware Main",
        icon="mdi:chip",
        shadow_field=SHADOW_FW_MAIN,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BroanSensorDescription(
        key="fw_ui",
        name="Firmware UI",
        icon="mdi:chip",
        shadow_field=SHADOW_FW_UI,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BroanSensorDescription(
        key="ota_available",
        name="Update Available",
        icon="mdi:update",
        shadow_field=SHADOW_OTA_AVAILABLE,
        as_int=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BroanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        BroanSensor(coordinator, entry, desc) for desc in SENSOR_DESCRIPTIONS
    )


class BroanSensor(CoordinatorEntity[BroanCoordinator], SensorEntity):
    entity_description: BroanSensorDescription

    def __init__(
        self,
        coordinator: BroanCoordinator,
        entry: ConfigEntry,
        description: BroanSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_uid}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_uid)},
            name=coordinator.device_name,
            manufacturer="Broan-NuTone",
        )

    @property
    def native_value(self) -> Any:
        desc = self.entity_description
        raw = self.coordinator.get_shadow_value(desc.shadow_field, as_int=desc.as_int)
        if raw is None:
            return None
        if desc.value_map:
            return desc.value_map.get(raw, raw)
        return raw
