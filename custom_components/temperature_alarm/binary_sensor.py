"""Binary sensor platform for Temperature Alarm integration."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback, CALLBACK_TYPE
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_call_later

from .const import (
    CONF_CREATE_MAX_ENTITY,
    CONF_CREATE_MIN_ENTITY,
    CONF_DELAY_ENABLED,
    CONF_DELAY_TIME,
    CONF_DELAY_UPDATES,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DEFAULT_DELAY_TIME,
    DEFAULT_DELAY_UPDATES,
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
    ], update_before_add=True)


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
        
        # Delay configuration
        self._delay_enabled = entry.data.get(CONF_DELAY_ENABLED, False)
        self._delay_time = entry.data.get(CONF_DELAY_TIME, DEFAULT_DELAY_TIME)
        self._delay_updates = entry.data.get(CONF_DELAY_UPDATES, DEFAULT_DELAY_UPDATES)
        
        # Delay tracking state
        self._alarm_pending_since: float | None = None
        self._alarm_update_count: int = 0
        self._delay_timer_cancel: CALLBACK_TYPE | None = None
        
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
        self.async_write_ha_state()

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
            self._reset_delay_tracking()
            return
        
        try:
            current_temp = float(source_state.state)
        except (ValueError, TypeError):
            self._attr_is_on = None
            self._attr_available = False
            self._reset_delay_tracking()
            return
        
        self._attr_available = True
        
        # Get threshold values - try entity first, fall back to config
        min_temp = self._get_threshold_value("min")
        max_temp = self._get_threshold_value("max")
        
        _LOGGER.debug(
            "Temperature Alarm update: current=%.2f, min_threshold=%s, max_threshold=%s, mode=%s",
            current_temp,
            min_temp,
            max_temp,
            self._mode,
        )
        
        # Evaluate alarm condition based on mode
        is_alarm_condition = False
        
        if self._mode == MODE_MIN_ONLY:
            if min_temp is not None:
                is_alarm_condition = current_temp < min_temp
        elif self._mode == MODE_MAX_ONLY:
            if max_temp is not None:
                is_alarm_condition = current_temp > max_temp
        elif self._mode == MODE_MIN_MAX:
            if min_temp is not None and current_temp < min_temp:
                is_alarm_condition = True
            if max_temp is not None and current_temp > max_temp:
                is_alarm_condition = True
        
        # Apply delay logic if enabled
        if self._delay_enabled and is_alarm_condition:
            self._handle_delay_logic(is_alarm_condition)
        elif is_alarm_condition:
            # No delay, trigger immediately
            self._attr_is_on = True
            self._reset_delay_tracking()
        else:
            # Condition not met, reset
            self._attr_is_on = False
            self._reset_delay_tracking()
        
        _LOGGER.debug("Alarm state: %s (condition: %s, delay_enabled: %s)", 
                      self._attr_is_on, is_alarm_condition, self._delay_enabled)

    def _get_threshold_value(self, threshold_type: str) -> float | None:
        """Get threshold value from entity or fall back to config."""
        if threshold_type == "min":
            entity = self._min_threshold_entity
            config_key = CONF_MIN_TEMP
        else:
            entity = self._max_threshold_entity
            config_key = CONF_MAX_TEMP
        
        # Try to get from entity first
        if entity is not None:
            try:
                value = entity.native_value
                if value is not None:
                    return float(value)
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Fall back to config value
        return self._entry.data.get(config_key)

    @callback
    def _handle_delay_logic(self, is_alarm_condition: bool) -> None:
        """Handle delay logic for alarm triggering."""
        current_time = time.monotonic()
        
        if is_alarm_condition:
            # Start tracking if not already
            if self._alarm_pending_since is None:
                self._alarm_pending_since = current_time
                self._alarm_update_count = 0
                _LOGGER.debug("Delay started: pending_since=%s", self._alarm_pending_since)
                
                # Schedule a timer callback for time-based delay
                self._schedule_delay_check()
            
            # Increment update counter
            self._alarm_update_count += 1
            
            # Check if delay criteria is met (either time OR updates)
            elapsed_time = current_time - self._alarm_pending_since
            time_met = elapsed_time >= self._delay_time
            updates_met = self._alarm_update_count >= self._delay_updates
            
            _LOGGER.debug(
                "Delay check: elapsed=%.1fs (need %ds), updates=%d (need %d), time_met=%s, updates_met=%s",
                elapsed_time, self._delay_time, self._alarm_update_count, self._delay_updates,
                time_met, updates_met
            )
            
            if time_met or updates_met:
                self._attr_is_on = True
                _LOGGER.debug("Delay criteria met, alarm triggered")
            else:
                # Still waiting, keep alarm off
                self._attr_is_on = False
        else:
            # Condition no longer met, reset tracking
            self._reset_delay_tracking()
            self._attr_is_on = False

    @callback
    def _reset_delay_tracking(self) -> None:
        """Reset delay tracking state."""
        self._alarm_pending_since = None
        self._alarm_update_count = 0
        
        # Cancel any pending timer
        if self._delay_timer_cancel is not None:
            self._delay_timer_cancel()
            self._delay_timer_cancel = None

    def _schedule_delay_check(self) -> None:
        """Schedule a callback to check delay after time elapses."""
        # Cancel any existing timer
        if self._delay_timer_cancel is not None:
            self._delay_timer_cancel()
        
        @callback
        def _delay_timer_callback(_now: Any) -> None:
            """Handle delay timer expiration."""
            self._delay_timer_cancel = None
            # Re-evaluate state - the time delay has elapsed
            self._update_state()
            self.async_write_ha_state()
        
        self._delay_timer_cancel = async_call_later(
            self.hass, self._delay_time, _delay_timer_callback
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs: dict[str, Any] = {
            "source_entity": self._source_entity_id,
            "mode": self._mode,
        }
        
        # Add current temperature
        if self.hass:
            source_state = self.hass.states.get(self._source_entity_id)
            if source_state and source_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                try:
                    attrs["current_temperature"] = float(source_state.state)
                except (ValueError, TypeError):
                    pass
        
        # Add threshold values based on mode
        if self._mode in (MODE_MIN_ONLY, MODE_MIN_MAX):
            min_temp = self._get_threshold_value("min")
            if min_temp is not None:
                attrs["min_threshold"] = min_temp
        
        if self._mode in (MODE_MAX_ONLY, MODE_MIN_MAX):
            max_temp = self._get_threshold_value("max")
            if max_temp is not None:
                attrs["max_threshold"] = max_temp
        
        # Add delay info if enabled
        if self._delay_enabled:
            attrs["delay_enabled"] = True
            attrs["delay_time"] = self._delay_time
            attrs["delay_updates"] = self._delay_updates
            if self._alarm_pending_since is not None:
                attrs["alarm_pending"] = True
                attrs["alarm_pending_updates"] = self._alarm_update_count
        
        return attrs
