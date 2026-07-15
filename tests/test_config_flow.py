"""Tests for the config and options flows.

Covers the "show all sensors" toggle (filtered vs unfiltered picker),
the numeric-Reading requirement on every selection, that the toggle
never leaks into entry data, and the Alarm Device Class choice on the
mode step of both flows.
"""
import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.temperature_alarm.const import (
    CONF_DEVICE_CLASS,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SHOW_ALL_SENSORS,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    MODE_MIN_MAX,
)

SOURCE = "sensor.attic_temperature"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """The flow handler lookup needs the custom integration loadable."""


def _entity_selector_config(result) -> dict:
    for marker, sel in result["data_schema"].schema.items():
        if str(marker) == CONF_SOURCE_ENTITY:
            return sel.config
    raise KeyError(CONF_SOURCE_ENTITY)


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


# picker filtering


async def test_picker_defaults_to_temperature_class(hass):
    result = await _start(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert _entity_selector_config(result)["device_class"] == ["temperature"]


async def test_toggle_reshows_unfiltered_picker(hass):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SHOW_ALL_SENSORS: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    config = _entity_selector_config(result)
    assert "device_class" not in config
    assert config["domain"] == ["sensor"]


# numeric-Reading requirement (both picker paths)


async def test_classless_numeric_sensor_accepted(hass):
    hass.states.async_set("sensor.attic_diy", "21.5")

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SHOW_ALL_SENSORS: True}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SOURCE_ENTITY: "sensor.attic_diy", CONF_SHOW_ALL_SENSORS: True},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mode"


async def test_non_numeric_state_rejected(hass):
    hass.states.async_set("sensor.attic_diy", "on")

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SOURCE_ENTITY: "sensor.attic_diy", CONF_SHOW_ALL_SENSORS: True},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "state_not_numeric"}


async def test_unavailable_temperature_sensor_rejected(hass):
    # the numeric check applies on the default (temperature-class) path too
    hass.states.async_set(
        SOURCE, "unavailable", {"device_class": "temperature"}
    )

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE_ENTITY: SOURCE}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "state_not_numeric"}


async def test_missing_entity_rejected(hass):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE_ENTITY: "sensor.ghost"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_entity"}


# end to end: entry created, toggle not persisted


async def test_full_flow_creates_entry_without_toggle_key(hass):
    hass.states.async_set("sensor.attic_diy", "21.5")

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SOURCE_ENTITY: "sensor.attic_diy", CONF_SHOW_ALL_SENSORS: True},
    )
    assert result["step_id"] == "mode"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "thresholds"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "delay"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SOURCE_ENTITY] == "sensor.attic_diy"
    assert CONF_SHOW_ALL_SENSORS not in result["data"]


# Alarm Device Class: chosen on the mode step of both flows


async def test_chosen_device_class_stored_in_entry_data(hass):
    hass.states.async_set("sensor.attic_diy", "21.5")

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SOURCE_ENTITY: "sensor.attic_diy", CONF_SHOW_ALL_SENSORS: True},
    )
    assert result["step_id"] == "mode"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_CLASS: "cold"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_CLASS] == "cold"


async def test_options_flow_updates_device_class(hass):
    hass.states.async_set(
        SOURCE, "21.5", {"device_class": "temperature", "unit_of_measurement": "°C"}
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE_ENTITY: SOURCE,
            CONF_MODE: MODE_MIN_MAX,
            CONF_MIN_TEMP: 5.0,
            CONF_MAX_TEMP: 30.0,
            CONF_DEVICE_CLASS: "problem",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_DEVICE_CLASS: "safety"}
    )
    assert result["step_id"] == "thresholds"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["step_id"] == "delay"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DEVICE_CLASS] == "safety"
