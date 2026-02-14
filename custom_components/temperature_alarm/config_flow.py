"""Config flow for Temperature Alarm integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_MODE,
    DOMAIN,
    MAX_TEMP_LIMIT,
    MIN_TEMP_LIMIT,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
    MODES,
    TEMP_STEP,
)

_LOGGER = logging.getLogger(__name__)


def _get_entity_unit(hass: HomeAssistant, entity_id: str) -> str:
    """Get the unit of measurement for an entity."""
    state = hass.states.get(entity_id)
    if state and state.attributes.get("unit_of_measurement"):
        return state.attributes.get("unit_of_measurement")
    return UnitOfTemperature.CELSIUS


class TemperatureAlarmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Temperature Alarm."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._unit: str = UnitOfTemperature.CELSIUS

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - select source entity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_SOURCE_ENTITY]
            
            # Check if already configured
            await self.async_set_unique_id(f"{DOMAIN}_{entity_id}")
            self._abort_if_unique_id_configured()
            
            # Validate the entity
            state = self.hass.states.get(entity_id)
            if state is None:
                errors["base"] = "invalid_entity"
            else:
                # Store selected entity and get its unit
                self._data[CONF_SOURCE_ENTITY] = entity_id
                self._unit = _get_entity_unit(self.hass, entity_id)
                return await self.async_step_mode()

        # Show entity selector
        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class=SensorDeviceClass.TEMPERATURE,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the mode selection step."""
        if user_input is not None:
            self._data[CONF_MODE] = user_input[CONF_MODE]
            return await self.async_step_thresholds()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=DEFAULT_MODE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=MODE_MIN_ONLY,
                                label="Minimum Only (alert when too cold)",
                            ),
                            selector.SelectOptionDict(
                                value=MODE_MAX_ONLY,
                                label="Maximum Only (alert when too hot)",
                            ),
                            selector.SelectOptionDict(
                                value=MODE_MIN_MAX,
                                label="Min/Max Range (alert when outside range)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="mode",
            data_schema=schema,
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the threshold configuration step."""
        errors: dict[str, str] = {}
        mode = self._data[CONF_MODE]

        if user_input is not None:
            min_temp = user_input.get(CONF_MIN_TEMP)
            max_temp = user_input.get(CONF_MAX_TEMP)

            # Validate min < max for min_max mode
            if mode == MODE_MIN_MAX and min_temp is not None and max_temp is not None:
                if min_temp >= max_temp:
                    errors["base"] = "min_greater_than_max"

            if not errors:
                self._data[CONF_MIN_TEMP] = min_temp
                self._data[CONF_MAX_TEMP] = max_temp

                # Create friendly title
                entity_reg = er.async_get(self.hass)
                entity_entry = entity_reg.async_get(self._data[CONF_SOURCE_ENTITY])
                if entity_entry and entity_entry.name:
                    title = f"{entity_entry.name} Alarm"
                else:
                    title = f"Temperature Alarm ({self._data[CONF_SOURCE_ENTITY]})"

                return self.async_create_entry(title=title, data=self._data)

        # Build schema based on mode
        schema_dict: dict[Any, Any] = {}

        if mode in (MODE_MIN_ONLY, MODE_MIN_MAX):
            schema_dict[vol.Required(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP)] = (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_TEMP_LIMIT,
                        max=MAX_TEMP_LIMIT,
                        step=TEMP_STEP,
                        unit_of_measurement=self._unit,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            )

        if mode in (MODE_MAX_ONLY, MODE_MIN_MAX):
            schema_dict[vol.Required(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP)] = (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_TEMP_LIMIT,
                        max=MAX_TEMP_LIMIT,
                        step=TEMP_STEP,
                        unit_of_measurement=self._unit,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            )

        return self.async_show_form(
            step_id="thresholds",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return TemperatureAlarmOptionsFlow(config_entry)


class TemperatureAlarmOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Temperature Alarm."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        errors: dict[str, str] = {}
        
        current_mode = self._config_entry.data.get(CONF_MODE, DEFAULT_MODE)
        current_min = self._config_entry.data.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
        current_max = self._config_entry.data.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
        source_entity = self._config_entry.data.get(CONF_SOURCE_ENTITY)
        
        unit = _get_entity_unit(self.hass, source_entity)

        if user_input is not None:
            new_mode = user_input.get(CONF_MODE, current_mode)
            new_min = user_input.get(CONF_MIN_TEMP)
            new_max = user_input.get(CONF_MAX_TEMP)

            # Validate min < max for min_max mode
            if new_mode == MODE_MIN_MAX and new_min is not None and new_max is not None:
                if new_min >= new_max:
                    errors["base"] = "min_greater_than_max"

            if not errors:
                # Update the config entry data
                new_data = {
                    **self._config_entry.data,
                    CONF_MODE: new_mode,
                }
                if new_min is not None:
                    new_data[CONF_MIN_TEMP] = new_min
                if new_max is not None:
                    new_data[CONF_MAX_TEMP] = new_max

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_MODE, default=current_mode): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=MODE_MIN_ONLY,
                            label="Minimum Only (alert when too cold)",
                        ),
                        selector.SelectOptionDict(
                            value=MODE_MAX_ONLY,
                            label="Maximum Only (alert when too hot)",
                        ),
                        selector.SelectOptionDict(
                            value=MODE_MIN_MAX,
                            label="Min/Max Range (alert when outside range)",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_MIN_TEMP, default=current_min): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_TEMP_LIMIT,
                    max=MAX_TEMP_LIMIT,
                    step=TEMP_STEP,
                    unit_of_measurement=unit,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_MAX_TEMP, default=current_max): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_TEMP_LIMIT,
                    max=MAX_TEMP_LIMIT,
                    step=TEMP_STEP,
                    unit_of_measurement=unit,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
