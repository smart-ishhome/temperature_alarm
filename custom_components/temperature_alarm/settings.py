"""Alarm Settings for the Temperature Alarm integration.

Owns what a user decides about one alarm: which fields a Monitoring
Mode requires, the schemas for editing them, and the rules that
validate them. The config and options flows are adapters over it —
they show these schemas and store the results, nothing more.

Schema builders take a ``defaults`` mapping: the config flow passes
an empty one (built-in defaults apply), the options flow passes the
entry data so forms are prefilled with current values.
"""
from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers import selector

from .const import (
    CONF_CREATE_MAX_ENTITY,
    CONF_CREATE_MIN_ENTITY,
    CONF_DELAY_ENABLED,
    CONF_DELAY_TIME,
    CONF_DELAY_UPDATES,
    CONF_DEVICE_CLASS,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    DEFAULT_DELAY_TIME,
    DEFAULT_DELAY_UPDATES,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_MODE,
    MAX_TEMP_LIMIT,
    MIN_TEMP_LIMIT,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
    TEMP_STEP,
)

Settings = Mapping[str, Any]


def _temperature_selector(unit: str | None) -> selector.NumberSelector:
    # A Source Sensor may report no unit; then the field renders unitless
    config: dict[str, Any] = {
        "min": MIN_TEMP_LIMIT,
        "max": MAX_TEMP_LIMIT,
        "step": TEMP_STEP,
        "mode": selector.NumberSelectorMode.BOX,
    }
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def mode_schema(defaults: Settings) -> vol.Schema:
    """Schema for choosing the Monitoring Mode and Alarm Device Class."""
    return vol.Schema(
        {
            vol.Required(
                CONF_MODE, default=defaults.get(CONF_MODE, DEFAULT_MODE)
            ): selector.SelectSelector(
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
            vol.Required(
                CONF_DEVICE_CLASS,
                default=defaults.get(CONF_DEVICE_CLASS, DEFAULT_DEVICE_CLASS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=BinarySensorDeviceClass.SAFETY.value,
                            label="Safety (reports Safe/Unsafe)",
                        ),
                        selector.SelectOptionDict(
                            value=BinarySensorDeviceClass.PROBLEM.value,
                            label="Problem (reports OK/Problem)",
                        ),
                        selector.SelectOptionDict(
                            value=BinarySensorDeviceClass.HEAT.value,
                            label="Heat (reports Normal/Hot)",
                        ),
                        selector.SelectOptionDict(
                            value=BinarySensorDeviceClass.COLD.value,
                            label="Cold (reports Normal/Cold)",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def thresholds_schema(mode: str, defaults: Settings, unit: str | None) -> vol.Schema:
    """Schema for the Thresholds a Monitoring Mode requires."""
    schema_dict: dict[Any, Any] = {}

    if mode in (MODE_MIN_ONLY, MODE_MIN_MAX):
        schema_dict[
            vol.Required(
                CONF_MIN_TEMP,
                default=defaults.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP),
            )
        ] = _temperature_selector(unit)
        schema_dict[
            vol.Required(
                CONF_CREATE_MIN_ENTITY,
                default=defaults.get(CONF_CREATE_MIN_ENTITY, True),
            )
        ] = selector.BooleanSelector()

    if mode in (MODE_MAX_ONLY, MODE_MIN_MAX):
        schema_dict[
            vol.Required(
                CONF_MAX_TEMP,
                default=defaults.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP),
            )
        ] = _temperature_selector(unit)
        schema_dict[
            vol.Required(
                CONF_CREATE_MAX_ENTITY,
                default=defaults.get(CONF_CREATE_MAX_ENTITY, True),
            )
        ] = selector.BooleanSelector()

    return vol.Schema(schema_dict)


def delay_schema(defaults: Settings) -> vol.Schema:
    """Schema for the Trigger Delay."""
    return vol.Schema(
        {
            vol.Required(
                CONF_DELAY_ENABLED,
                default=defaults.get(CONF_DELAY_ENABLED, False),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_DELAY_TIME,
                default=defaults.get(CONF_DELAY_TIME, DEFAULT_DELAY_TIME),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=3600,
                    step=1,
                    unit_of_measurement="seconds",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_DELAY_UPDATES,
                default=defaults.get(CONF_DELAY_UPDATES, DEFAULT_DELAY_UPDATES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=100,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def validate(settings: Settings) -> dict[str, str]:
    """Validate the settings; returns flow-style errors, empty when valid.

    The min < max rule only applies in min_max mode — in the single-sided
    modes the other Threshold is not compared against.
    """
    if settings.get(CONF_MODE) == MODE_MIN_MAX:
        min_temp = settings.get(CONF_MIN_TEMP)
        max_temp = settings.get(CONF_MAX_TEMP)
        if min_temp is not None and max_temp is not None and min_temp >= max_temp:
            return {"base": "min_greater_than_max"}
    return {}
