"""Select entities for Broan Range Hood."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    FAN_AUTO_SENSITIVITY_HIGH,
    FAN_AUTO_SENSITIVITY_LOW,
    FAN_AUTO_SENSITIVITY_MEDIUM,
    LIGHT_MODE_ON,
    SHADOW_FAN_AUTO_SENSITIVITY,
    SHADOW_FAN_MODE,
    SHADOW_FAN_SPEED,
    SHADOW_FAN_STATE,
    SHADOW_FACTORY_SETTINGS,
    SHADOW_LIGHT_INTENSITY,
    SHADOW_LIGHT_STATE,
    FAN_MODE_OFF,
    FAN_MODE_ON,
)
from .coordinator import BroanCoordinator
from .factory import parse_factory_settings

_SENSITIVITY_OPTIONS = ["Low", "Medium", "High"]
_SENSITIVITY_MAP = {
    FAN_AUTO_SENSITIVITY_LOW: "Low",
    FAN_AUTO_SENSITIVITY_MEDIUM: "Medium",
    FAN_AUTO_SENSITIVITY_HIGH: "High",
}
_SENSITIVITY_REVERSE = {v: k for k, v in _SENSITIVITY_MAP.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BroanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BroanFanSpeedSelect(coordinator, entry),
            BroanLightLevelSelect(coordinator, entry),
            BroanAutoSensitivitySelect(coordinator, entry),
        ]
    )


def _fan_speed_options(factory_bytes: str | None) -> list[str]:
    speed_count = parse_factory_settings(factory_bytes).fan_speeds or 3
    labels = ["Low", "Medium", "High", "Max"]
    if speed_count <= len(labels):
        return labels[:speed_count]
    return [f"Speed {idx}" for idx in range(1, speed_count + 1)]


def _light_level_options(factory_bytes: str | None) -> list[str]:
    level_count = parse_factory_settings(factory_bytes).light_levels or 2
    labels = ["Low", "High"]
    if level_count == 2:
        return labels
    return [f"Level {idx}" for idx in range(1, level_count + 1)]


def _option_to_step(options: list[str], option: str) -> int | None:
    try:
        return options.index(option) + 1
    except ValueError:
        return None


class _BroanSelectEntity(CoordinatorEntity[BroanCoordinator], SelectEntity):
    """Shared Broan select entity base."""

    def __init__(self, coordinator: BroanCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_uid)},
            name=coordinator.device_name,
            manufacturer="Broan-NuTone",
        )


class BroanFanSpeedSelect(_BroanSelectEntity):
    """Explicit discrete fan speed selector."""

    _attr_has_entity_name = True
    _attr_name = "Fan Speed"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: BroanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_fan_speed"

    @property
    def options(self) -> list[str]:
        return _fan_speed_options(self.coordinator.get_shadow_value(SHADOW_FACTORY_SETTINGS))

    @property
    def current_option(self) -> str | None:
        step = self.coordinator.get_shadow_value(SHADOW_FAN_SPEED, as_int=True)
        if not step:
            return None
        options = self.options
        if 1 <= step <= len(options):
            return options[step - 1]
        return None

    async def async_select_option(self, option: str) -> None:
        step = _option_to_step(self.options, option)
        if step is None:
            return
        self.coordinator.set_property(SHADOW_FAN_MODE, FAN_MODE_OFF)
        self.coordinator.set_property(SHADOW_FAN_SPEED, step)
        self.coordinator.set_property(SHADOW_FAN_STATE, FAN_MODE_ON)


class BroanLightLevelSelect(_BroanSelectEntity):
    """Explicit discrete light level selector."""

    _attr_has_entity_name = True
    _attr_name = "Light Level"
    _attr_icon = "mdi:brightness-6"

    def __init__(self, coordinator: BroanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_light_level"

    @property
    def options(self) -> list[str]:
        return _light_level_options(
            self.coordinator.get_shadow_value(SHADOW_FACTORY_SETTINGS)
        )

    @property
    def current_option(self) -> str | None:
        step = self.coordinator.get_shadow_value(SHADOW_LIGHT_INTENSITY, as_int=True)
        if not step:
            return None
        options = self.options
        if 1 <= step <= len(options):
            return options[step - 1]
        return None

    async def async_select_option(self, option: str) -> None:
        step = _option_to_step(self.options, option)
        if step is None:
            return
        self.coordinator.set_property(SHADOW_LIGHT_INTENSITY, step)
        self.coordinator.set_property(SHADOW_LIGHT_STATE, LIGHT_MODE_ON)


class BroanAutoSensitivitySelect(_BroanSelectEntity):
    """
    IntelliVent™ auto-operation sensitivity selector.

    Controls how sensitive the hood is to cooking odours / air quality
    when running in Auto mode.
    """

    _attr_has_entity_name = True
    _attr_name = "Auto Mode Sensitivity"
    _attr_options = _SENSITIVITY_OPTIONS
    _attr_icon = "mdi:tune"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BroanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_auto_sensitivity"

    @property
    def current_option(self) -> str | None:
        val = self.coordinator.get_shadow_value(SHADOW_FAN_AUTO_SENSITIVITY, as_int=True)
        if val is None:
            return None
        return _SENSITIVITY_MAP.get(val)

    async def async_select_option(self, option: str) -> None:
        val = _SENSITIVITY_REVERSE.get(option)
        if val is not None:
            self.coordinator.set_property(SHADOW_FAN_AUTO_SENSITIVITY, val)
