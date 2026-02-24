"""Number platform for Temperature Alarm integration."""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CREATE_MAX_ENTITY,
    CONF_CREATE_MIN_ENTITY,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN,
    MAX_TEMP_LIMIT,
    MIN_TEMP_LIMIT,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
    TEMP_STEP,
)

_LOGGER = logging.getLogger(__name__)


def _get_entity_unit(hass: HomeAssistant, entity_id: str) -> str:
    """Get the unit of measurement for an entity."""
    state = hass.states.get(entity_id)
    if state and state.attributes.get("unit_of_measurement"):
        return state.attributes.get("unit_of_measurement")
    return UnitOfTemperature.CELSIUS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Temperature Alarm number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    source_entity_id = data["source_entity_id"]
    device_info = data.get("device_info")
    
    mode = entry.data.get(CONF_MODE, MODE_MIN_MAX)
    initial_min = entry.data.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
    initial_max = entry.data.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
    create_min_entity = entry.data.get(CONF_CREATE_MIN_ENTITY, True)
    create_max_entity = entry.data.get(CONF_CREATE_MAX_ENTITY, True)
    
    _LOGGER.debug(
        "Number entity setup: mode=%s, create_min=%s, create_max=%s, min_temp=%s, max_temp=%s",
        mode,
        create_min_entity,
        create_max_entity,
        initial_min,
        initial_max,
    )
    
    unit = _get_entity_unit(hass, source_entity_id)
    
    entities: list[TemperatureThresholdNumber] = []
    min_entity: TemperatureThresholdNumber | None = None
    max_entity: TemperatureThresholdNumber | None = None
    
    # Create min temperature entity if needed and user wants it as an entity
    if mode in (MODE_MIN_ONLY, MODE_MIN_MAX) and create_min_entity:
        min_entity = TemperatureThresholdNumber(
            entry=entry,
            source_entity_id=source_entity_id,
            device_info=device_info,
            threshold_type="min",
            initial_value=initial_min,
            unit=unit,
        )
        entities.append(min_entity)
        _LOGGER.debug("Created min temperature entity")
    
    # Create max temperature entity if needed and user wants it as an entity
    if mode in (MODE_MAX_ONLY, MODE_MIN_MAX) and create_max_entity:
        max_entity = TemperatureThresholdNumber(
            entry=entry,
            source_entity_id=source_entity_id,
            device_info=device_info,
            threshold_type="max",
            initial_value=initial_max,
            unit=unit,
        )
        entities.append(max_entity)
        _LOGGER.debug("Created max temperature entity")
    
    # Store references to threshold entities for binary sensor to use
    data["min_threshold_entity"] = min_entity
    data["max_threshold_entity"] = max_entity
    
    _LOGGER.debug("Adding %d number entities", len(entities))
    async_add_entities(entities)


class TemperatureThresholdNumber(RestoreNumber, NumberEntity):
    """Number entity for temperature threshold."""

    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_TEMP_LIMIT
    _attr_native_max_value = MAX_TEMP_LIMIT
    _attr_native_step = TEMP_STEP

    def __init__(
        self,
        entry: ConfigEntry,
        source_entity_id: str,
        device_info: dict[str, Any] | None,
        threshold_type: str,
        initial_value: float,
        unit: str,
    ) -> None:
        """Initialize the number entity."""
        self._entry = entry
        self._source_entity_id = source_entity_id
        self._threshold_type = threshold_type
        self._initial_value = initial_value
        self._attr_native_value = initial_value
        self._attr_native_unit_of_measurement = unit
        self._update_callbacks: list[Callable[[], None]] = []
        
        _LOGGER.debug(
            "Initializing %s threshold entity with value %.2f %s",
            threshold_type,
            initial_value,
            unit,
        )
        
        # Set unique ID and translation key
        self._attr_unique_id = (
            f"{DOMAIN}_{source_entity_id}_{threshold_type}_temperature"
        )
        self._attr_translation_key = f"{threshold_type}_temperature"
        
        # Set icon based on threshold type
        if threshold_type == "min":
            self._attr_icon = "mdi:thermometer-minus"
        else:
            self._attr_icon = "mdi:thermometer-plus"
        
        # Device info - attach to source device if available
        if device_info:
            self._attr_device_info = DeviceInfo(**device_info)

    def register_update_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when the value changes."""
        self._update_callbacks.append(callback)

    async def async_added_to_hass(self) -> None:
        """Restore previous state when added to hass."""
        await super().async_added_to_hass()
        
        _LOGGER.debug(
            "%s threshold entity added - initial_value=%.2f, current native_value=%.2f, unit=%s",
            self._threshold_type,
            self._initial_value,
            self._attr_native_value if self._attr_native_value is not None else 0,
            self._attr_native_unit_of_measurement,
        )
        
        # Try to restore previous value
        last_number_data = await self.async_get_last_number_data()
        if last_number_data and last_number_data.native_value is not None:
            self._attr_native_value = last_number_data.native_value
            _LOGGER.debug(
                "Restored %s threshold to %.2f from previous state (unit: %s)",
                self._threshold_type,
                self._attr_native_value,
                self._attr_native_unit_of_measurement,
            )
        else:
            # Use initial value from config
            self._attr_native_value = self._initial_value
            _LOGGER.debug(
                "Using initial %s threshold value %.2f from config (unit: %s)",
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
        
        # Notify registered callbacks that the threshold changed
        for callback in self._update_callbacks:
            callback()

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return self._attr_native_unit_of_measurement
