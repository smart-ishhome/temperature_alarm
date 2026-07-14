"""Binary sensor platform for Temperature Alarm integration.

This entity is the adapter between Home Assistant and the Alarm
Evaluator (evaluator.py): it resolves the reading and Thresholds, feeds
them to the evaluator, and applies the resulting Verdict to HA state.
All alarm semantics live in the evaluator.
"""
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
from .evaluator import AlarmEvaluator, Thresholds, Trigger, Verdict

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
    _attr_icon = "mdi:thermometer-alert"
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

        # Delay configuration (kept for extra_state_attributes)
        self._delay_enabled = entry.data.get(CONF_DELAY_ENABLED, False)
        self._delay_time = entry.data.get(CONF_DELAY_TIME, DEFAULT_DELAY_TIME)
        self._delay_updates = entry.data.get(CONF_DELAY_UPDATES, DEFAULT_DELAY_UPDATES)

        # All alarm semantics live in the evaluator
        self._evaluator = AlarmEvaluator(
            mode=mode,
            delay_enabled=self._delay_enabled,
            delay_time=self._delay_time,
            delay_updates=self._delay_updates,
        )
        self._last_verdict: Verdict | None = None
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

        # Make sure a pending re-check timer never fires after removal
        self.async_on_remove(self._cancel_delay_timer)

        # Initial state evaluation - reads the source for the first time
        self._refresh(Trigger.SOURCE_UPDATE)

    @callback
    def _async_threshold_changed(self) -> None:
        """Handle threshold value changes."""
        _LOGGER.debug("Threshold changed, re-evaluating alarm state")
        self._refresh(Trigger.THRESHOLD_CHANGE)

    @callback
    def _async_source_state_changed(self, event: Event) -> None:
        """Handle state changes of source temperature entity."""
        _LOGGER.debug("Source entity state changed: %s", event.data.get("new_state"))
        self._refresh(Trigger.SOURCE_UPDATE)

    @callback
    def _refresh(self, trigger: Trigger) -> None:
        """Evaluate the alarm and apply the Verdict to HA state."""
        reading = self._current_reading()
        thresholds = self._current_thresholds()

        verdict = self._evaluator.evaluate(
            reading, thresholds, time.monotonic(), trigger
        )
        self._last_verdict = verdict

        _LOGGER.debug(
            "Temperature Alarm update: reading=%s, thresholds=%s, mode=%s -> %s",
            reading,
            thresholds,
            self._mode,
            verdict,
        )

        self._attr_available = verdict.available
        self._attr_is_on = verdict.is_on

        # Timer management: a Verdict without pending obsoletes any
        # scheduled re-check; recheck_in asks for a (re)scheduled one.
        if not verdict.pending:
            self._cancel_delay_timer()
        if verdict.recheck_in is not None:
            self._schedule_recheck(verdict.recheck_in)

        self.async_write_ha_state()

    def _current_reading(self) -> float | None:
        """Read the source temperature, or None if unavailable/non-numeric."""
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is None or source_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return None
        try:
            return float(source_state.state)
        except (ValueError, TypeError):
            return None

    def _current_thresholds(self) -> Thresholds:
        """Resolve the current Thresholds for the evaluator."""
        return Thresholds(
            min=self._get_threshold_value("min"),
            max=self._get_threshold_value("max"),
        )

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
                    _LOGGER.debug(
                        "Using %s threshold from entity: %.2f",
                        threshold_type,
                        value,
                    )
                    return float(value)
                else:
                    _LOGGER.debug(
                        "%s threshold entity exists but value is None, falling back to config",
                        threshold_type,
                    )
            except (ValueError, TypeError, AttributeError) as err:
                _LOGGER.debug(
                    "Error getting %s threshold from entity: %s, falling back to config",
                    threshold_type,
                    err,
                )

        # Fall back to config value
        config_value = self._entry.data.get(config_key)
        _LOGGER.debug(
            "Using %s threshold from config: %s",
            threshold_type,
            config_value,
        )
        return config_value

    @callback
    def _cancel_delay_timer(self) -> None:
        """Cancel any scheduled delay re-check."""
        if self._delay_timer_cancel is not None:
            self._delay_timer_cancel()
            self._delay_timer_cancel = None

    def _schedule_recheck(self, delay: float) -> None:
        """Schedule a re-evaluation after the delay the Verdict asked for."""
        self._cancel_delay_timer()

        @callback
        def _delay_timer_callback(_now: Any) -> None:
            """Handle delay timer expiration."""
            self._delay_timer_cancel = None
            self._refresh(Trigger.RECHECK)

        self._delay_timer_cancel = async_call_later(
            self.hass, delay, _delay_timer_callback
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
            if self._last_verdict is not None and self._last_verdict.pending:
                attrs["alarm_pending"] = True
                attrs["alarm_pending_updates"] = self._last_verdict.pending_updates

        return attrs
