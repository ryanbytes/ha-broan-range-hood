"""Switch entities for Broan Range Hood."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DELAY_OFF_DISABLED,
    DELAY_OFF_ENABLED,
    DOMAIN,
    SHADOW_FAN_DELAY_OFF,
)
from .coordinator import BroanCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BroanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BroanDelayOffSwitch(coordinator, entry)])


class BroanDelayOffSwitch(CoordinatorEntity[BroanCoordinator], SwitchEntity):
    """
    Delay-Off switch.

    When enabled, the fan runs for a set period after being turned off
    to clear residual cooking odours.
    """

    _attr_has_entity_name = True
    _attr_name = "Delay Off"
    _attr_icon = "mdi:fan-clock"

    def __init__(self, coordinator: BroanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_delay_off"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_uid)},
            name=coordinator.device_name,
            manufacturer="Broan-NuTone",
        )

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.get_shadow_value(SHADOW_FAN_DELAY_OFF, as_int=True)
        if state is None:
            return None
        return state == DELAY_OFF_ENABLED

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_property(SHADOW_FAN_DELAY_OFF, DELAY_OFF_ENABLED)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_property(SHADOW_FAN_DELAY_OFF, DELAY_OFF_DISABLED)
