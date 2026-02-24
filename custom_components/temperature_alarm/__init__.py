"""The Temperature Alarm integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CREATE_MAX_ENTITY,
    CONF_CREATE_MIN_ENTITY,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Temperature Alarm from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    source_entity_id = entry.data[CONF_SOURCE_ENTITY]
    
    # Get device info from source entity
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    
    device_id = None
    device_info = None
    
    source_entry = entity_registry.async_get(source_entity_id)
    if source_entry and source_entry.device_id:
        device_id = source_entry.device_id
        device = device_registry.async_get(device_id)
        if device:
            # Get the primary identifier for the device
            device_info = {
                "identifiers": device.identifiers,
            }
    
    # Store data for platforms
    hass.data[DOMAIN][entry.entry_id] = {
        "source_entity_id": source_entity_id,
        "device_id": device_id,
        "device_info": device_info,
    }
    
    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register update listener for options flow
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Options updated, reloading integration for entry %s", entry.entry_id)
    _LOGGER.debug("New data: %s", entry.data)
    
    # Get entity registry
    entity_registry = er.async_get(hass)
    source_entity_id = entry.data.get(CONF_SOURCE_ENTITY)
    
    # Check if we need to remove entities
    create_min = entry.data.get(CONF_CREATE_MIN_ENTITY, True)
    create_max = entry.data.get(CONF_CREATE_MAX_ENTITY, True)
    mode = entry.data.get(CONF_MODE, MODE_MIN_MAX)
    
    # Remove min threshold entity if it should not exist
    if not create_min or mode not in (MODE_MIN_ONLY, MODE_MIN_MAX):
        min_unique_id = f"{DOMAIN}_{source_entity_id}_min_temperature"
        entity_id = entity_registry.async_get_entity_id("number", DOMAIN, min_unique_id)
        if entity_id:
            _LOGGER.debug("Removing min threshold entity: %s", entity_id)
            entity_registry.async_remove(entity_id)
    
    # Remove max threshold entity if it should not exist
    if not create_max or mode not in (MODE_MAX_ONLY, MODE_MIN_MAX):
        max_unique_id = f"{DOMAIN}_{source_entity_id}_max_temperature"
        entity_id = entity_registry.async_get_entity_id("number", DOMAIN, max_unique_id)
        if entity_id:
            _LOGGER.debug("Removing max threshold entity: %s", entity_id)
            entity_registry.async_remove(entity_id)
    
    # Reload the config entry to apply new options
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok
