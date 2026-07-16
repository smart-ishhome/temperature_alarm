"""Shared helpers for the HA-facing test files.

Owns two facts the test tier would otherwise encode per file: the
canonical config entry (SOURCE / BASE_DATA / make_entry) and schema
introspection over rendered voluptuous schemas, whose markers only
compare by str(). Imported only by the HA-facing test files, so the
evaluator-only CI (conftest.collect_ignore) never loads it.
"""
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.temperature_alarm.const import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    MODE_MIN_MAX,
)

SOURCE = "sensor.garage_temperature"

BASE_DATA = {
    CONF_SOURCE_ENTITY: SOURCE,
    CONF_MODE: MODE_MIN_MAX,
    CONF_MIN_TEMP: 5.0,
    CONF_MAX_TEMP: 30.0,
}


def make_entry(**overrides):
    """The canonical entry, with these values changed (update-only)."""
    return MockConfigEntry(domain=DOMAIN, data={**BASE_DATA, **overrides})


# Schema introspection


def keys(schema: vol.Schema) -> set[str]:
    return {str(key) for key in schema.schema}


def default_of(schema: vol.Schema, key: str):
    for marker in schema.schema:
        if str(marker) == key:
            return marker.default()
    raise KeyError(key)


def selector_config(schema: vol.Schema, key: str) -> dict:
    for marker, sel in schema.schema.items():
        if str(marker) == key:
            return sel.config
    raise KeyError(key)
