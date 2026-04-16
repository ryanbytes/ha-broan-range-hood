"""Broan Range Hood integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_DEVICE_NAME, CONF_SERIAL_NUMBER, DOMAIN
from .coordinator import BroanCoordinator
from .factory import parse_factory_settings

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Broan from a config entry."""
    coordinator = BroanCoordinator(
        hass=hass,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        serial_number=entry.data[CONF_SERIAL_NUMBER],
        device_name=entry.data.get(CONF_DEVICE_NAME, "Range Hood"),
        device_uid=entry.unique_id or entry.entry_id,
    )

    try:
        await coordinator.async_setup()
    except Exception as exc:
        raise ConfigEntryNotReady(f"Could not connect to Broan device: {exc}") from exc

    preferred_uid = _get_preferred_device_uid(entry, coordinator)
    if preferred_uid:
        coordinator.device_uid = preferred_uid
        if entry.unique_id != preferred_uid:
            hass.config_entries.async_update_entry(
                entry,
                unique_id=preferred_uid,
            )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _async_remove_duplicate_entities(hass, entry, coordinator)
    _async_remove_duplicate_device(hass, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: BroanCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


def _async_remove_duplicate_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: BroanCoordinator,
) -> None:
    """Remove entities created from the mutable cloud thing name."""
    if coordinator.device_uid == coordinator.thing_name:
        return

    entity_registry = er.async_get(hass)
    stale_prefix = f"{coordinator.thing_name}_"

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if entity_entry.unique_id.startswith(stale_prefix):
            entity_registry.async_remove(entity_entry.entity_id)


def _async_remove_duplicate_device(
    hass: HomeAssistant,
    coordinator: BroanCoordinator,
) -> None:
    """Remove the extra device created when using the cloud thing name as the UID."""
    if coordinator.device_uid == coordinator.thing_name:
        return

    device_registry = dr.async_get(hass)
    stale_device = device_registry.async_get_device(
        identifiers={(DOMAIN, coordinator.thing_name)}
    )
    if stale_device:
        device_registry.async_remove_device(stale_device.id)


def _get_preferred_device_uid(
    entry: ConfigEntry,
    coordinator: BroanCoordinator,
) -> str:
    """Prefer the printed serial from factory settings over the cloud thing name."""
    factory = parse_factory_settings(coordinator.get_shadow_value("0x0f0a"))
    if factory.printed_serial:
        return factory.printed_serial
    return entry.unique_id or entry.data.get(CONF_SERIAL_NUMBER) or coordinator.device_uid
