"""Tests for Threshold Resolution (thresholds.py).

Covers the module's whole interface: which Threshold Entities should
exist, value precedence (Threshold Entity first, config fallback), and
change notification.
"""
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.temperature_alarm.const import (
    CONF_CREATE_MAX_ENTITY,
    CONF_CREATE_MIN_ENTITY,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    MODE_MAX_ONLY,
    MODE_MIN_ONLY,
    MODE_MIN_MAX,
)
from custom_components.temperature_alarm.thresholds import (
    ThresholdResolver,
    async_remove_orphaned_entities,
    threshold_unique_id,
    wants_entity,
)

SOURCE = "sensor.garage_temperature"


def make_entry(**overrides):
    data = {
        CONF_SOURCE_ENTITY: SOURCE,
        CONF_MODE: MODE_MIN_MAX,
        CONF_MIN_TEMP: 5.0,
        CONF_MAX_TEMP: 30.0,
    }
    data.update(overrides)
    return MockConfigEntry(domain=DOMAIN, data=data)


def register_threshold_entity(hass, kind):
    """Register a Threshold Entity the way the number platform would."""
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "number",
        DOMAIN,
        threshold_unique_id(SOURCE, kind),
        suggested_object_id=f"garage_{kind}_threshold",
    )
    return entry.entity_id


# wants_entity — which Threshold Entities should exist


def test_wants_both_by_default():
    entry = make_entry()
    assert wants_entity(entry.data, "min")
    assert wants_entity(entry.data, "max")


def test_mode_excludes_other_side():
    min_only = make_entry(**{CONF_MODE: MODE_MIN_ONLY})
    assert wants_entity(min_only.data, "min")
    assert not wants_entity(min_only.data, "max")

    max_only = make_entry(**{CONF_MODE: MODE_MAX_ONLY})
    assert not wants_entity(max_only.data, "min")
    assert wants_entity(max_only.data, "max")


def test_create_flag_disables_entity():
    entry = make_entry(**{CONF_CREATE_MIN_ENTITY: False})
    assert not wants_entity(entry.data, "min")
    assert wants_entity(entry.data, "max")


# current() — precedence and fallback


async def test_config_fallback_without_entities(hass):
    resolver = ThresholdResolver(hass, make_entry())
    thresholds = resolver.current()
    assert thresholds.min == 5.0
    assert thresholds.max == 30.0


async def test_entity_value_wins(hass):
    entity_id = register_threshold_entity(hass, "min")
    hass.states.async_set(entity_id, "7.5")
    resolver = ThresholdResolver(hass, make_entry())
    thresholds = resolver.current()
    assert thresholds.min == 7.5
    assert thresholds.max == 30.0  # no max entity -> config


async def test_registered_entity_without_state_falls_back(hass):
    register_threshold_entity(hass, "min")
    resolver = ThresholdResolver(hass, make_entry())
    assert resolver.current().min == 5.0


async def test_unavailable_entity_falls_back(hass):
    entity_id = register_threshold_entity(hass, "min")
    hass.states.async_set(entity_id, "unavailable")
    resolver = ThresholdResolver(hass, make_entry())
    assert resolver.current().min == 5.0


async def test_non_numeric_state_falls_back(hass):
    entity_id = register_threshold_entity(hass, "min")
    hass.states.async_set(entity_id, "banana")
    resolver = ThresholdResolver(hass, make_entry())
    assert resolver.current().min == 5.0


async def test_absent_config_side_is_none(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE_ENTITY: SOURCE,
            CONF_MODE: MODE_MIN_MAX,
            CONF_MIN_TEMP: 5.0,
        },
    )
    resolver = ThresholdResolver(hass, entry)
    assert resolver.current().max is None


# async_subscribe — change notification


async def test_subscribe_fires_on_threshold_change(hass):
    entity_id = register_threshold_entity(hass, "min")
    hass.states.async_set(entity_id, "5.0")
    resolver = ThresholdResolver(hass, make_entry())

    calls = []
    unsub = resolver.async_subscribe(lambda: calls.append(1))

    hass.states.async_set(entity_id, "6.0")
    await hass.async_block_till_done()
    assert len(calls) == 1

    unsub()
    hass.states.async_set(entity_id, "7.0")
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_subscribe_without_entities_is_noop(hass):
    entry = make_entry(
        **{CONF_CREATE_MIN_ENTITY: False, CONF_CREATE_MAX_ENTITY: False}
    )
    resolver = ThresholdResolver(hass, entry)
    unsub = resolver.async_subscribe(lambda: None)
    unsub()  # must not raise


# async_remove_orphaned_entities — prune on reconfigure


async def test_remove_orphaned_entities_prunes_unwanted_kind(hass):
    min_id = register_threshold_entity(hass, "min")
    max_id = register_threshold_entity(hass, "max")

    async_remove_orphaned_entities(hass, make_entry(**{CONF_MODE: MODE_MAX_ONLY}))

    registry = er.async_get(hass)
    assert registry.async_get(min_id) is None
    assert registry.async_get(max_id) is not None
