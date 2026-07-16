"""Number platform for Temperature Alarm integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AlarmRuntimeData
from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_THRESHOLD_UNIT,
    DOMAIN,
    KINDS,
    MAX_TEMP_LIMIT,
    MIN_TEMP_LIMIT,
    TEMP_STEP,
)
from .reading import unit_of
from .thresholds import (
    convert_threshold,
    is_temperature_unit,
    threshold_unique_id,
    wants_entity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Temperature Alarm number entities."""
    data: AlarmRuntimeData = hass.data[DOMAIN][entry.entry_id]

    unit = unit_of(hass.states.get(data.source_entity_id))

    # Config values remember the unit they were saved in; reconcile
    # them to the unit the entity announces today. A side without a
    # config value seeds nothing - the entity starts unknown.
    saved_unit = entry.data.get(CONF_THRESHOLD_UNIT)
    initial_value = {
        "min": convert_threshold(entry.data.get(CONF_MIN_TEMP), saved_unit, unit),
        "max": convert_threshold(entry.data.get(CONF_MAX_TEMP), saved_unit, unit),
    }

    entities = [
        TemperatureThresholdNumber(
            entry=entry,
            source_entity_id=data.source_entity_id,
            device_info=data.device_info,
            threshold_type=kind,
            initial_value=initial_value[kind],
            unit=unit,
        )
        for kind in KINDS
        if wants_entity(entry.data, kind)
    ]

    _LOGGER.debug("Adding %d number entities", len(entities))
    async_add_entities(entities)


class TemperatureThresholdNumber(RestoreNumber, NumberEntity):
    """Number entity for temperature threshold."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_TEMP_LIMIT
    _attr_native_max_value = MAX_TEMP_LIMIT
    _attr_native_step = TEMP_STEP

    def __init__(
        self,
        entry: ConfigEntry,
        source_entity_id: str,
        device_info: DeviceInfo | None,
        threshold_type: str,
        initial_value: float | None,
        unit: str | None,
    ) -> None:
        """Initialize the number entity."""
        self._entry = entry
        self._source_entity_id = source_entity_id
        self._threshold_type = threshold_type
        self._initial_value = initial_value
        self._attr_native_value = initial_value
        self._attr_native_unit_of_measurement = unit
        # Announce as a temperature only when the source's unit really
        # is one; a unitless or non-temperature source gets no class.
        self._attr_device_class = (
            NumberDeviceClass.TEMPERATURE if is_temperature_unit(unit) else None
        )

        _LOGGER.debug(
            "Initializing %s threshold entity with value %s %s",
            threshold_type,
            initial_value,
            unit,
        )

        # Set unique ID and translation key
        self._attr_unique_id = threshold_unique_id(source_entity_id, threshold_type)
        self._attr_translation_key = f"{threshold_type}_temperature"
        
        # Set icon based on threshold type
        if threshold_type == "min":
            self._attr_icon = "mdi:thermometer-minus"
        else:
            self._attr_icon = "mdi:thermometer-plus"
        
        # Device info - attach to source device if available
        if device_info:
            self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        """Restore previous state when added to hass."""
        await super().async_added_to_hass()
        
        _LOGGER.debug(
            "%s threshold entity added - initial_value=%s, current native_value=%s, unit=%s",
            self._threshold_type,
            self._initial_value,
            self._attr_native_value,
            self._attr_native_unit_of_measurement,
        )
        
        # Try to restore previous value. It comes back with the unit it
        # was saved under; reconcile it to the unit announced today.
        last_number_data = await self.async_get_last_number_data()
        if last_number_data and last_number_data.native_value is not None:
            self._attr_native_value = convert_threshold(
                last_number_data.native_value,
                last_number_data.native_unit_of_measurement,
                self._attr_native_unit_of_measurement,
            )
            _LOGGER.debug(
                "Restored %s threshold to %s from previous state (unit: %s)",
                self._threshold_type,
                self._attr_native_value,
                self._attr_native_unit_of_measurement,
            )
        else:
            # Use initial value from config
            self._attr_native_value = self._initial_value
            _LOGGER.debug(
                "Using initial %s threshold value %s from config (unit: %s)",
                self._threshold_type,
                self._initial_value,
                self._attr_native_unit_of_measurement,
            )
        
        # Write the state after restoration
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        _LOGGER.debug(
            "Setting %s threshold to %.2f (unit: %s)",
            self._threshold_type,
            value,
            self._attr_native_unit_of_measurement,
        )
        self._attr_native_value = value
        self.async_write_ha_state()
