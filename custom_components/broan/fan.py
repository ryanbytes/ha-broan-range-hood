"""Fan entity for Broan Range Hood."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import (
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    FAN_MODE_AUTO,
    FAN_MODE_OFF,
    FAN_MODE_ON,
    SHADOW_FAN_MODE,
    SHADOW_FAN_SPEED,
    SHADOW_FAN_STATE,
    SHADOW_FACTORY_SETTINGS,
)
from .coordinator import BroanCoordinator
from .factory import parse_factory_settings

# Default max speeds if factory settings haven't been read yet
_DEFAULT_SPEEDS = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BroanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BroanFan(coordinator, entry)])


def _parse_num_speeds(factory_bytes: str | None) -> int:
    """Parse numberOfFanSpeed from the device factory settings string."""
    return parse_factory_settings(factory_bytes).fan_speeds or _DEFAULT_SPEEDS


def _speed_to_percentage(speed: int, num_speeds: int) -> int:
    """Convert a discrete Broan speed into a Home Assistant percentage."""
    return round((speed / num_speeds) * 100)


def _percentage_to_speed(percentage: int, num_speeds: int) -> int:
    """Map a Home Assistant percentage to the nearest discrete Broan speed."""
    return max(1, min(num_speeds, round((percentage / 100) * num_speeds)))


class BroanFan(CoordinatorEntity[BroanCoordinator], FanEntity):
    """Represents the range hood fan."""

    _attr_has_entity_name = True
    _attr_name = "Fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = ["auto"]

    def __init__(self, coordinator: BroanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_fan"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_uid)},
            name=coordinator.device_name,
            manufacturer="Broan-NuTone",
            model=coordinator.device_uid,
        )

    # ------------------------------------------------------------------
    @property
    def _num_speeds(self) -> int:
        fs = self.coordinator.get_shadow_value(SHADOW_FACTORY_SETTINGS)
        return _parse_num_speeds(fs)

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.get_shadow_value(SHADOW_FAN_STATE, as_int=True)
        if state is None:
            return None
        return bool(state)

    @property
    def percentage(self) -> int | None:
        if not self.is_on:
            return 0
        speed = self.coordinator.get_shadow_value(SHADOW_FAN_SPEED, as_int=True)
        if speed is None:
            return None
        return _speed_to_percentage(speed, self._num_speeds)

    @property
    def speed_count(self) -> int:
        return self._num_speeds

    @property
    def preset_mode(self) -> str | None:
        mode = self.coordinator.get_shadow_value(SHADOW_FAN_MODE, as_int=True)
        if mode == FAN_MODE_AUTO:
            return "auto"
        return None

    # ------------------------------------------------------------------
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if preset_mode == "auto":
            self.coordinator.set_property(SHADOW_FAN_MODE, FAN_MODE_AUTO)
            self.coordinator.set_property(SHADOW_FAN_STATE, FAN_MODE_ON)
        else:
            self.coordinator.set_property(SHADOW_FAN_MODE, FAN_MODE_OFF)
            if percentage is not None:
                speed = _percentage_to_speed(percentage, self._num_speeds)
            else:
                current_speed = self.coordinator.get_shadow_value(
                    SHADOW_FAN_SPEED, as_int=True
                )
                speed = current_speed if current_speed and current_speed > 0 else 1

            self.coordinator.set_property(SHADOW_FAN_SPEED, speed)
            self.coordinator.set_property(SHADOW_FAN_STATE, FAN_MODE_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_property(SHADOW_FAN_STATE, FAN_MODE_OFF)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        self.coordinator.set_property(SHADOW_FAN_MODE, FAN_MODE_OFF)
        speed = _percentage_to_speed(percentage, self._num_speeds)
        self.coordinator.set_property(SHADOW_FAN_SPEED, speed)
        # Ensure fan is on
        if not self.is_on:
            self.coordinator.set_property(SHADOW_FAN_STATE, FAN_MODE_ON)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == "auto":
            self.coordinator.set_property(SHADOW_FAN_MODE, FAN_MODE_AUTO)
            self.coordinator.set_property(SHADOW_FAN_STATE, FAN_MODE_ON)
        else:
            self.coordinator.set_property(SHADOW_FAN_MODE, FAN_MODE_OFF)
