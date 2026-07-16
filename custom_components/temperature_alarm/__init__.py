"""The Temperature Alarm integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_SOURCE_ENTITY, DOMAIN, PLATFORMS
from .thresholds import async_remove_orphaned_entities

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlarmRuntimeData:
    """What the composition root resolves for the platforms.

    device_info is ready-made: the Source Sensor's device attachment,
    or None when the source has no device. Stored in hass.data (the
    test harness's ConfigEntry predates entry.runtime_data).
    """

    source_entity_id: str
    device_info: DeviceInfo | None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Temperature Alarm from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    source_entity_id = entry.data[CONF_SOURCE_ENTITY]

    # Attach to the Source Sensor's device if it has one
    device_info = None
    source_entry = er.async_get(hass).async_get(source_entity_id)
    if source_entry and source_entry.device_id:
        device = dr.async_get(hass).async_get(source_entry.device_id)
        if device:
            device_info = DeviceInfo(identifiers=device.identifiers)

    hass.data[DOMAIN][entry.entry_id] = AlarmRuntimeData(
        source_entity_id=source_entity_id,
        device_info=device_info,
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
