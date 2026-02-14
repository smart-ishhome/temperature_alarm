"""Binary sensor platform for Temperature Alarm integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Temperature Alarm binary sensor."""
    data = hass.data[DOMAIN][entry.entry_id]
    source_entity_id = data["source_entity_id"]
    device_info = data.get("device_info")
    mode = entry.data.get(CONF_MODE, MODE_MIN_MAX)
    
    # Get threshold entity references from number platform
    min_threshold_entity = data.get("min_threshold_entity")
    max_threshold_entity = data.get("max_threshold_entity")
    
    async_add_entities([
        TemperatureAlarmBinarySensor(
            entry=entry,
            source_entity_id=source_entity_id,
            device_info=device_info,
            mode=mode,
            min_threshold_entity=min_threshold_entity,
            max_threshold_entity=max_threshold_entity,
        )
    ])


class TemperatureAlarmBinarySensor(BinarySensorEntity):
    """Binary sensor for temperature alarm state."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "temperature_alarm"
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        source_entity_id: str,
        device_info: dict[str, Any] | None,
        mode: str,
        min_threshold_entity: Any | None = None,
        max_threshold_entity: Any | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        self._entry = entry
        self._source_entity_id = source_entity_id
        self._mode = mode
        self._attr_is_on = None
        
        # Store direct references to threshold entities
        self._min_threshold_entity = min_threshold_entity
        self._max_threshold_entity = max_threshold_entity
        
        # Set unique ID
        self._attr_unique_id = f"{DOMAIN}_{source_entity_id}_alarm"
        
        # Device info - attach to source device if available
        if device_info:
            self._attr_device_info = DeviceInfo(**device_info)

    async def async_added_to_hass(self) -> None:
        """Set up state tracking when added to hass."""
        await super().async_added_to_hass()
        
        _LOGGER.debug(
            "Temperature Alarm for %s: mode=%s, has_min_entity=%s, has_max_entity=%s",
            self._source_entity_id,
            self._mode,
            self._min_threshold_entity is not None,
            self._max_threshold_entity is not None,
        )
        
        # Track source temperature entity for state changes
        # We read threshold values directly from the entity objects, not via state machine
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._source_entity_id],
                self._async_source_state_changed,
            )
        )
        
        # Register callbacks with threshold entities to re-evaluate when thresholds change
        if self._min_threshold_entity is not None:
            self._min_threshold_entity.register_update_callback(
                self._async_threshold_changed
            )
        if self._max_threshold_entity is not None:
            self._max_threshold_entity.register_update_callback(
                self._async_threshold_changed
            )
        
        # Initial state evaluation
        self._update_state()

    @callback
    def _async_threshold_changed(self) -> None:
        """Handle threshold value changes."""
        _LOGGER.debug("Threshold changed, re-evaluating alarm state")
        self._update_state()
        self.async_write_ha_state()

    @callback
    def _async_source_state_changed(self, event: Event) -> None:
        """Handle state changes of source temperature entity."""
        _LOGGER.debug("Source entity state changed: %s", event.data.get("new_state"))
        self._update_state()
        self.async_write_ha_state()

    @callback
    def _update_state(self) -> None:
        """Update the alarm state based on current temperature and thresholds."""
        # Get source temperature
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is None or source_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            self._attr_is_on = None
            self._attr_available = False
            return
        
        try:
            current_temp = float(source_state.state)
        except (ValueError, TypeError):
            self._attr_is_on = None
            self._attr_available = False
            return
        
        self._attr_available = True
        
        # Get threshold values directly from entity objects
        min_temp = self._get_threshold_value_direct(self._min_threshold_entity)
        max_temp = self._get_threshold_value_direct(self._max_threshold_entity)
        
        _LOGGER.debug(
            "Temperature Alarm update: current=%.2f, min_threshold=%s, max_threshold=%s, mode=%s",
            current_temp,
            min_temp,
            max_temp,
            self._mode,
        )
        
        # Evaluate alarm condition based on mode
        is_alarm = False
        
        if self._mode == MODE_MIN_ONLY:
            if min_temp is not None:
                is_alarm = current_temp < min_temp
        elif self._mode == MODE_MAX_ONLY:
            if max_temp is not None:
                is_alarm = current_temp > max_temp
        elif self._mode == MODE_MIN_MAX:
            if min_temp is not None and current_temp < min_temp:
                is_alarm = True
            if max_temp is not None and current_temp > max_temp:
                is_alarm = True
        
        _LOGGER.debug("Alarm state: %s (was: %s)", is_alarm, self._attr_is_on)
        self._attr_is_on = is_alarm

    def _get_threshold_value_direct(self, entity: Any | None) -> float | None:
        """Get threshold value directly from a number entity object."""
        if entity is None:
            return None
        
        try:
            value = entity.native_value
            if value is not None:
                return float(value)
        except (ValueError, TypeError, AttributeError):
            pass
        
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs: dict[str, Any] = {
            "source_entity": self._source_entity_id,
            "mode": self._mode,
        }
        
        # Add current temperature
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state and source_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            try:
                attrs["current_temperature"] = float(source_state.state)
            except (ValueError, TypeError):
                pass
        
        # Add threshold values from entity objects
        min_temp = self._get_threshold_value_direct(self._min_threshold_entity)
        max_temp = self._get_threshold_value_direct(self._max_threshold_entity)
        
        if min_temp is not None:
            attrs["min_threshold"] = min_temp
        if max_temp is not None:
            attrs["max_threshold"] = max_temp
        
        return attrs
