"""Tests for Alarm Settings (settings.py).

Covers the module's whole interface: which fields each Monitoring Mode
requires, defaults threading (built-in vs entry data), and validation.
Schema construction needs homeassistant importable but no running hass.
"""
import voluptuous as vol

from custom_components.temperature_alarm.const import (
    CONF_CREATE_MAX_ENTITY,
    CONF_CREATE_MIN_ENTITY,
    CONF_DELAY_ENABLED,
    CONF_DELAY_TIME,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    DEFAULT_DELAY_TIME,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_MODE,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
)
from custom_components.temperature_alarm.settings import (
    delay_schema,
    mode_schema,
    thresholds_schema,
    validate,
)


def keys(schema: vol.Schema) -> set[str]:
    return {str(key) for key in schema.schema}


def default_of(schema: vol.Schema, key: str):
    for marker in schema.schema:
        if str(marker) == key:
            return marker.default()
    raise KeyError(key)


# which fields a Monitoring Mode requires


def test_min_only_has_only_min_fields():
    schema = thresholds_schema(MODE_MIN_ONLY, {}, "°C")
    assert keys(schema) == {CONF_MIN_TEMP, CONF_CREATE_MIN_ENTITY}


def test_max_only_has_only_max_fields():
    schema = thresholds_schema(MODE_MAX_ONLY, {}, "°C")
    assert keys(schema) == {CONF_MAX_TEMP, CONF_CREATE_MAX_ENTITY}


def test_min_max_has_both_sides():
    schema = thresholds_schema(MODE_MIN_MAX, {}, "°C")
    assert keys(schema) == {
        CONF_MIN_TEMP,
        CONF_CREATE_MIN_ENTITY,
        CONF_MAX_TEMP,
        CONF_CREATE_MAX_ENTITY,
    }


# defaults threading: built-in defaults vs entry data


def test_built_in_defaults_apply_without_entry_data():
    assert default_of(mode_schema({}), CONF_MODE) == DEFAULT_MODE
    schema = thresholds_schema(MODE_MIN_MAX, {}, "°C")
    assert default_of(schema, CONF_MIN_TEMP) == DEFAULT_MIN_TEMP
    assert default_of(schema, CONF_MAX_TEMP) == DEFAULT_MAX_TEMP
    assert default_of(schema, CONF_CREATE_MIN_ENTITY) is True
    assert default_of(delay_schema({}), CONF_DELAY_TIME) == DEFAULT_DELAY_TIME


def test_entry_data_prefills_defaults():
    data = {
        CONF_MODE: MODE_MAX_ONLY,
        CONF_MAX_TEMP: 42.0,
        CONF_CREATE_MAX_ENTITY: False,
        CONF_DELAY_ENABLED: True,
    }
    assert default_of(mode_schema(data), CONF_MODE) == MODE_MAX_ONLY
    schema = thresholds_schema(MODE_MAX_ONLY, data, "°C")
    assert default_of(schema, CONF_MAX_TEMP) == 42.0
    assert default_of(schema, CONF_CREATE_MAX_ENTITY) is False
    assert default_of(delay_schema(data), CONF_DELAY_ENABLED) is True


# validation


def test_min_at_or_above_max_rejected_in_min_max():
    settings = {CONF_MODE: MODE_MIN_MAX, CONF_MIN_TEMP: 30.0, CONF_MAX_TEMP: 5.0}
    assert validate(settings) == {"base": "min_greater_than_max"}
    settings = {CONF_MODE: MODE_MIN_MAX, CONF_MIN_TEMP: 5.0, CONF_MAX_TEMP: 5.0}
    assert validate(settings) == {"base": "min_greater_than_max"}


def test_valid_range_accepted():
    settings = {CONF_MODE: MODE_MIN_MAX, CONF_MIN_TEMP: 5.0, CONF_MAX_TEMP: 30.0}
    assert validate(settings) == {}


def test_rule_only_applies_in_min_max():
    # stale opposite-side values from an earlier mode must not reject
    settings = {CONF_MODE: MODE_MIN_ONLY, CONF_MIN_TEMP: 30.0, CONF_MAX_TEMP: 5.0}
    assert validate(settings) == {}


def test_missing_sides_accepted():
    assert validate({CONF_MODE: MODE_MIN_MAX, CONF_MIN_TEMP: 5.0}) == {}
    assert validate({CONF_MODE: MODE_MIN_MAX}) == {}
