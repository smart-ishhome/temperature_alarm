"""End-to-end test: config entry setup through Alarm state changes.

Drives the real wiring — platform setup order, the Alarm's state-bus
subscriptions (Source Sensor and Threshold Entities), and Verdict
application — not just the modules in isolation.
"""
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.temperature_alarm.const import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    MODE_MIN_MAX,
)
from custom_components.temperature_alarm.thresholds import threshold_unique_id

SOURCE = "sensor.garage_temperature"


async def test_alarm_follows_source_and_thresholds(hass, enable_custom_integrations):
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE_ENTITY: SOURCE,
            CONF_MODE: MODE_MIN_MAX,
            CONF_MIN_TEMP: 5.0,
            CONF_MAX_TEMP: 30.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    alarm_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{DOMAIN}_{SOURCE}_alarm"
    )
    max_threshold_id = registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "max")
    )
    assert alarm_id and max_threshold_id

    # In range -> off
    assert hass.states.get(alarm_id).state == "off"

    # Source crosses the max Threshold -> on
    hass.states.async_set(SOURCE, "40.0")
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "on"

    # Source recovers -> off
    hass.states.async_set(SOURCE, "20.0")
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "off"

    # Threshold Entity moves below the Reading -> on (state-bus subscription)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": max_threshold_id, "value": 15.0},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "on"

    # Source goes away -> Alarm unavailable
    hass.states.async_set(SOURCE, "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "unavailable"
