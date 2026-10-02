"""The Temperature Alarm integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import AnyDeviceEntry
from homeassistant.helpers.helper_integration import async_remove_helper_devices

from .const import CONF_SOURCE_ENTITY, DOMAIN, PLATFORMS
from .thresholds import async_remove_orphaned_entities

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlarmRuntimeData:
    """What the composition root resolves for the platforms.

    device is the Source Sensor's device, which the alarm's entities
    link to without owning it, or None when the Source Sensor has no
    device.
    Stored in hass.data.
    """

    source_entity_id: str
    device: AnyDeviceEntry | None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Temperature Alarm from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    source_entity_id = entry.data[CONF_SOURCE_ENTITY]
    device = async_entity_id_to_device(hass, source_entity_id)

    # An alarm owns no device. Remove any it does own (a device created
    # by 1.0.0 on HA 2026.8+, or HA's split of the formerly shared
    # device), relinking its entities to the source device first.
    async_remove_helper_devices(
        hass,
        helper_config_entry_id=entry.entry_id,
        source_device_id=device.id if device else None,
        remove_all_devices=True,
    )

    hass.data[DOMAIN][entry.entry_id] = AlarmRuntimeData(
        source_entity_id=source_entity_id,
        device=device,
    )
    
    # Threshold Entities must be registered before the Alarm looks them
    # up to subscribe, so the number platform is fully set up first.
    await hass.config_entries.async_forward_entry_setups(entry, ["number"])
    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor"])
    
    # Register update listener for options flow
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Options updated, reloading integration for entry %s", entry.entry_id)
    _LOGGER.debug("New data: %s", entry.data)
    
    # Reload the config entry to apply new options
    await hass.config_entries.async_reload(entry.entry_id)

    # Remove Threshold Entities that should no longer exist. This must
    # happen after the reload: removing a registry entry also removes its
    # live entity, and the reload's unload would then remove it a second
    # time, failing the whole unload.
    async_remove_orphaned_entities(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok
