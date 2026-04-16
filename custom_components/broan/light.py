"""Light entity for Broan Range Hood."""
from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LIGHT_MODE_AUTO,
    LIGHT_MODE_OFF,
    LIGHT_MODE_ON,
    SHADOW_LIGHT_INTENSITY,
    SHADOW_LIGHT_STATE,
)
from .coordinator import BroanCoordinator
from .factory import parse_factory_settings

_DEFAULT_LIGHT_LEVELS = 2


def _parse_num_light_levels(factory_bytes: str | None) -> int:
    """Parse the number of supported light intensity levels."""
    return parse_factory_settings(factory_bytes).light_levels or _DEFAULT_LIGHT_LEVELS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BroanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BroanLight(coordinator, entry)])


class BroanLight(CoordinatorEntity[BroanCoordinator], LightEntity):
    """Represents the range hood light."""

    _attr_has_entity_name = True
    _attr_name = "Light"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: BroanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_light"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_uid)},
            name=coordinator.device_name,
            manufacturer="Broan-NuTone",
        )

    @property
    def _num_light_levels(self) -> int:
        fs = self.coordinator.get_shadow_value("0x0f0a")
        return _parse_num_light_levels(fs)

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.get_shadow_value(SHADOW_LIGHT_STATE, as_int=True)
        if state is None:
            return None
        return state == LIGHT_MODE_ON

    @property
    def brightness(self) -> int | None:
        intensity = self.coordinator.get_shadow_value(SHADOW_LIGHT_INTENSITY, as_int=True)
        if intensity is None:
            return None

        # Broan reports discrete steps (2 levels on this hood), not a full 0-100 scale.
        level = max(1, min(intensity, self._num_light_levels))
        return round((level / self._num_light_levels) * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            intensity = max(
                1,
                math.ceil((kwargs[ATTR_BRIGHTNESS] / 255) * self._num_light_levels),
            )
            self.coordinator.set_property(SHADOW_LIGHT_INTENSITY, intensity)
        self.coordinator.set_property(SHADOW_LIGHT_STATE, LIGHT_MODE_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_property(SHADOW_LIGHT_STATE, LIGHT_MODE_OFF)
