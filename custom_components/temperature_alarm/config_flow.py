"""Config flow for Temperature Alarm integration.

Both flows here are thin adapters over Alarm Settings (settings.py):
they show its schemas, run its validation, and store the results. The
options flow mirrors the config flow's steps (minus source selection)
so each form only shows the fields the chosen Monitoring Mode requires.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import CONF_MODE, CONF_SHOW_ALL_SENSORS, CONF_SOURCE_ENTITY, DOMAIN
from .reading import reading_of, unit_of
from .settings import delay_schema, mode_schema, thresholds_schema, validate

_LOGGER = logging.getLogger(__name__)


class TemperatureAlarmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Temperature Alarm."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._unit: str | None = None
        self._show_all: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - select source entity.

        The picker is filtered to temperature-class sensors by default;
        the "show all sensors" toggle re-shows it unfiltered so sensors
        without a device_class can be chosen. Whatever the path, the
        selection must have a live numeric Reading right now.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            self._show_all = user_input.get(CONF_SHOW_ALL_SENSORS, False)
            entity_id = user_input.get(CONF_SOURCE_ENTITY)

            if entity_id:
                # Check if already configured
                await self.async_set_unique_id(f"{DOMAIN}_{entity_id}")
                self._abort_if_unique_id_configured()

                state = self.hass.states.get(entity_id)
                if state is None:
                    errors["base"] = "invalid_entity"
                elif reading_of(state) is None:
                    errors["base"] = "state_not_numeric"

                if not errors:
                    self._data[CONF_SOURCE_ENTITY] = entity_id
                    self._unit = unit_of(state)
                    return await self.async_step_mode()
            # No entity picked: the user flipped the toggle - just re-show

        if self._show_all:
            entity_selector = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
        else:
            entity_selector = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class=SensorDeviceClass.TEMPERATURE,
                )
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_SOURCE_ENTITY): entity_selector,
                vol.Required(
                    CONF_SHOW_ALL_SENSORS, default=self._show_all
                ): selector.BooleanSelector(),
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
            self._data.update(user_input)
            return await self.async_step_thresholds()

        return self.async_show_form(
            step_id="mode",
            data_schema=mode_schema(self._data),
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the threshold configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = validate({**self._data, **user_input})
            if not errors:
                self._data.update(user_input)
                return await self.async_step_delay()

        return self.async_show_form(
            step_id="thresholds",
            data_schema=thresholds_schema(
                self._data[CONF_MODE], self._data, self._unit
            ),
            errors=errors,
        )

    async def async_step_delay(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the trigger delay configuration step."""
        if user_input is not None:
            self._data.update(user_input)

            # Create friendly title
            entity_reg = er.async_get(self.hass)
            entity_entry = entity_reg.async_get(self._data[CONF_SOURCE_ENTITY])
            if entity_entry and entity_entry.name:
                title = f"{entity_entry.name} Alarm"
            else:
                title = f"Temperature Alarm ({self._data[CONF_SOURCE_ENTITY]})"

            return self.async_create_entry(title=title, data=self._data)

        return self.async_show_form(
            step_id="delay",
            data_schema=delay_schema(self._data),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return TemperatureAlarmOptionsFlow(config_entry)


class TemperatureAlarmOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Temperature Alarm.

    Mirrors the config flow's steps (mode, thresholds, delay) with the
    entry's current data as defaults; the Source Sensor is fixed.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the mode selection step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_thresholds()

        return self.async_show_form(
            step_id="init",
            data_schema=mode_schema(self._data),
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the threshold configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = validate({**self._data, **user_input})
            if not errors:
                self._data.update(user_input)
                return await self.async_step_delay()

        unit = unit_of(self.hass.states.get(self._data[CONF_SOURCE_ENTITY]))
        return self.async_show_form(
            step_id="thresholds",
            data_schema=thresholds_schema(self._data[CONF_MODE], self._data, unit),
            errors=errors,
        )

    async def async_step_delay(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the trigger delay configuration step."""
        if user_input is not None:
            self._data.update(user_input)
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=self._data
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="delay",
            data_schema=delay_schema(self._data),
        )
