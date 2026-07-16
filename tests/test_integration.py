"""End-to-end test: config entry setup through Alarm state changes.

Drives the real wiring — platform setup order, the Alarm's state-bus
subscriptions (Source Sensor and Threshold Entities), Verdict
application, the Trigger Delay re-check timer, the options-update
reconciliation, and Threshold Entity restore-state — not just the
modules in isolation.
"""
from datetime import timedelta

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.temperature_alarm.const import (
    CONF_DELAY_ENABLED,
    CONF_DELAY_TIME,
    CONF_DELAY_UPDATES,
    CONF_DEVICE_CLASS,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    CONF_THRESHOLD_UNIT,
    DOMAIN,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
)
from custom_components.temperature_alarm.binary_sensor import alarm_unique_id
from custom_components.temperature_alarm.thresholds import threshold_unique_id

SOURCE = "sensor.garage_temperature"

BASE_DATA = {
    CONF_SOURCE_ENTITY: SOURCE,
    CONF_MODE: MODE_MIN_MAX,
    CONF_MIN_TEMP: 5.0,
    CONF_MAX_TEMP: 30.0,
}

DELAY_DATA = {
    **BASE_DATA,
    CONF_DELAY_ENABLED: True,
    CONF_DELAY_TIME: 30,
    CONF_DELAY_UPDATES: 3,
}


async def _setup_entry(hass, data):
    """Set up an entry for real and return (entry, alarm entity_id)."""
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    alarm_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, alarm_unique_id(SOURCE)
    )
    assert alarm_id
    return entry, alarm_id


async def test_alarm_follows_source_and_thresholds(hass, enable_custom_integrations):
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})

    _, alarm_id = await _setup_entry(hass, BASE_DATA)

    registry = er.async_get(hass)
    max_threshold_id = registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "max")
    )
    assert max_threshold_id

    # In range -> off, with the full attribute picture
    state = hass.states.get(alarm_id)
    assert state.state == "off"
    assert state.attributes["source_entity"] == SOURCE
    assert state.attributes["mode"] == MODE_MIN_MAX
    assert state.attributes["current_temperature"] == 20.0
    assert state.attributes["min_threshold"] == 5.0
    assert state.attributes["max_threshold"] == 30.0
    assert "delay_enabled" not in state.attributes
    assert "alarm_pending" not in state.attributes

    # No restore data: the Threshold Entity starts at its configured value
    assert hass.states.get(max_threshold_id).state == "30.0"

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


async def test_classless_unitless_source_works(hass, enable_custom_integrations):
    """A Source Sensor with no device_class and no unit still drives the Alarm.

    Its Threshold Entities must not invent a unit (°C fallback removed).
    """
    source = "sensor.attic_diy"
    hass.states.async_set(source, "20.0")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE_ENTITY: source,
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
        "binary_sensor", DOMAIN, alarm_unique_id(source)
    )
    max_threshold_id = registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(source, "max")
    )
    assert alarm_id and max_threshold_id

    # No unit invented on the Threshold Entity
    threshold_state = hass.states.get(max_threshold_id)
    assert threshold_state.attributes.get("unit_of_measurement") is None

    # Alarm still follows Readings
    assert hass.states.get(alarm_id).state == "off"
    hass.states.async_set(source, "40.0")
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "on"


async def test_source_unit_flip_converts_thresholds(
    hass, enable_custom_integrations
):
    """A Source Sensor unit change must not corrupt comparisons.

    The Threshold Entities keep their °C unit; Threshold Resolution
    converts their values to the source's new unit on every refresh.
    """
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})
    _, alarm_id = await _setup_entry(hass, BASE_DATA)
    assert hass.states.get(alarm_id).state == "off"

    # Source flips to °F: 80 °F is 26.7 °C, inside the 5-30 °C range.
    # A raw comparison against max=30 would wrongly alarm.
    hass.states.async_set(SOURCE, "80.0", {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()
    state = hass.states.get(alarm_id)
    assert state.state == "off"
    assert state.attributes["min_threshold"] == pytest.approx(41.0)  # 5 °C
    assert state.attributes["max_threshold"] == pytest.approx(86.0)  # 30 °C

    # 90 °F is 32.2 °C - genuinely above max -> on
    hass.states.async_set(SOURCE, "90.0", {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "on"


async def _alarm_state(hass, data):
    """Set up an entry with the given data and return the Alarm's state."""
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})

    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    alarm_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, alarm_unique_id(SOURCE)
    )
    return hass.states.get(alarm_id)


async def test_alarm_reports_configured_device_class(
    hass, enable_custom_integrations
):
    state = await _alarm_state(
        hass,
        {
            CONF_SOURCE_ENTITY: SOURCE,
            CONF_MODE: MODE_MIN_MAX,
            CONF_MIN_TEMP: 5.0,
            CONF_MAX_TEMP: 30.0,
            CONF_DEVICE_CLASS: "cold",
        },
    )
    assert state.attributes["device_class"] == "cold"


async def test_entry_without_device_class_stays_problem(
    hass, enable_custom_integrations
):
    # Entries from before the Alarm Device Class existed keep today's class
    state = await _alarm_state(
        hass,
        {
            CONF_SOURCE_ENTITY: SOURCE,
            CONF_MODE: MODE_MIN_MAX,
            CONF_MIN_TEMP: 5.0,
            CONF_MAX_TEMP: 30.0,
        },
    )
    assert state.attributes["device_class"] == "problem"


# Trigger Delay: the Verdict's recheck_in -> async_call_later -> RECHECK wiring


async def test_trigger_delay_defers_alarm_until_timer_fires(
    hass, enable_custom_integrations, freezer
):
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})
    _, alarm_id = await _setup_entry(hass, DELAY_DATA)
    assert hass.states.get(alarm_id).state == "off"

    # Violation starts Alarm Pending: still off, pending attributes exposed
    hass.states.async_set(SOURCE, "40.0")
    await hass.async_block_till_done()
    state = hass.states.get(alarm_id)
    assert state.state == "off"
    assert state.attributes["delay_enabled"] is True
    assert state.attributes["delay_time"] == 30
    assert state.attributes["delay_updates"] == 3
    assert state.attributes["alarm_pending"] is True
    assert state.attributes["alarm_pending_updates"] == 1

    # The scheduled re-check fires after the Trigger Delay -> on,
    # and Alarm Pending ends with it
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(alarm_id)
    assert state.state == "on"
    assert "alarm_pending" not in state.attributes


async def test_trigger_delay_recovery_is_immediate_and_stays_off(
    hass, enable_custom_integrations, freezer
):
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})
    _, alarm_id = await _setup_entry(hass, DELAY_DATA)

    hass.states.async_set(SOURCE, "40.0")
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).attributes.get("alarm_pending") is True

    # Recovery mid-delay -> off immediately, Alarm Pending cleared
    hass.states.async_set(SOURCE, "20.0")
    await hass.async_block_till_done()
    state = hass.states.get(alarm_id)
    assert state.state == "off"
    assert "alarm_pending" not in state.attributes

    # The obsolete re-check never flips the Alarm on
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "off"


# Options update: orphaned Threshold Entities are removed on reconfigure


async def test_options_mode_change_removes_orphaned_threshold_entity(
    hass, enable_custom_integrations
):
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})
    entry, alarm_id = await _setup_entry(hass, BASE_DATA)

    registry = er.async_get(hass)
    assert registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "min")
    )

    # Real options flow: Monitoring Mode min_max -> max_only
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "mode"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MODE: MODE_MAX_ONLY}
    )
    assert result["step_id"] == "thresholds"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["step_id"] == "delay"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # min Threshold Entity removed, max survives
    assert (
        registry.async_get_entity_id(
            "number", DOMAIN, threshold_unique_id(SOURCE, "min")
        )
        is None
    )
    assert registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "max")
    )

    # The reloaded Alarm is max_only: low Readings no longer alarm
    hass.states.async_set(SOURCE, "3.0")
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "off"
    hass.states.async_set(SOURCE, "40.0")
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "on"


# Restore-state: an adjusted Threshold survives a reload and beats the config


async def test_adjusted_threshold_survives_reload(hass, enable_custom_integrations):
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})
    entry, alarm_id = await _setup_entry(hass, BASE_DATA)

    registry = er.async_get(hass)
    max_threshold_id = registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "max")
    )

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": max_threshold_id, "value": 15.0},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "on"  # Reading 20 > adjusted 15

    # Reload: the restored 15.0 wins over the configured 30.0
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(max_threshold_id).state == "15.0"
    assert hass.states.get(alarm_id).state == "on"


async def test_absent_config_side_seeds_no_threshold(
    hass, enable_custom_integrations
):
    """A Threshold Entity with no config value starts unknown: its side
    has no Threshold until the user types one - no phantom default."""
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})
    _, alarm_id = await _setup_entry(
        hass,
        {CONF_SOURCE_ENTITY: SOURCE, CONF_MODE: MODE_MIN_MAX, CONF_MAX_TEMP: 30.0},
    )

    registry = er.async_get(hass)
    min_threshold_id = registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "min")
    )
    assert hass.states.get(min_threshold_id).state == "unknown"

    # 20 °C with no min Threshold -> off (a phantom 50 default would alarm)
    state = hass.states.get(alarm_id)
    assert state.state == "off"
    assert "min_threshold" not in state.attributes

    # Typing a value activates the side
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": min_threshold_id, "value": 25.0},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(alarm_id).state == "on"


async def test_restored_threshold_converts_from_stored_unit(
    hass, enable_custom_integrations
):
    """A restored Threshold is reconciled from the unit it was saved under.

    25 °C stored before a source unit flip must come back as 77 °F,
    not be re-read as 25 °F.
    """
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})
    entry, alarm_id = await _setup_entry(
        hass, {**BASE_DATA, CONF_THRESHOLD_UNIT: "°C"}
    )

    registry = er.async_get(hass)
    max_threshold_id = registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "max")
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": max_threshold_id, "value": 25.0},
        blocking=True,
    )
    await hass.async_block_till_done()

    # The source flips to °F, then the entry reloads (e.g. a restart)
    hass.states.async_set(SOURCE, "70.0", {"unit_of_measurement": "°F"})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # 25 °C restores as 77 °F; 70 °F (21.1 °C) stays below it -> off.
    # An unconverted restore would read 25 °F and wrongly alarm.
    state = hass.states.get(alarm_id)
    assert state.state == "off"
    assert state.attributes["max_threshold"] == pytest.approx(77.0)
    # HA renders temperature numbers in the system unit (°C here), so
    # the user still sees the 25 °C they set.
    assert float(hass.states.get(max_threshold_id).state) == pytest.approx(25.0)


async def test_seeded_threshold_converts_from_saved_unit(
    hass, enable_custom_integrations
):
    """A fresh Threshold Entity seeds its config value reconciled to the
    source's current unit (values saved under °C, source now °F)."""
    hass.states.async_set(SOURCE, "70.0", {"unit_of_measurement": "°F"})
    _, alarm_id = await _setup_entry(
        hass, {**BASE_DATA, CONF_THRESHOLD_UNIT: "°C"}
    )

    # Seeds converted to °F: 5 °C -> 41, 30 °C -> 86. An unconverted
    # seed would put max at 30 °F and wrongly alarm on 70 °F.
    state = hass.states.get(alarm_id)
    assert state.state == "off"
    assert state.attributes["min_threshold"] == pytest.approx(41.0)
    assert state.attributes["max_threshold"] == pytest.approx(86.0)

    # HA renders temperature numbers in the system unit (°C here), so
    # the user still sees the 5 °C they configured.
    registry = er.async_get(hass)
    min_threshold_id = registry.async_get_entity_id(
        "number", DOMAIN, threshold_unique_id(SOURCE, "min")
    )
    assert float(hass.states.get(min_threshold_id).state) == pytest.approx(5.0)


# Device attachment: entities land on the Source Sensor's device


async def test_entities_attach_to_source_device(hass, enable_custom_integrations):
    # A Source Sensor registered against a device
    source_config_entry = MockConfigEntry(domain="test")
    source_config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source_config_entry.entry_id,
        identifiers={("test", "garage-sensor-1")},
    )
    registry = er.async_get(hass)
    source = registry.async_get_or_create(
        "sensor",
        "test",
        "garage-temp",
        device_id=device.id,
        suggested_object_id="garage_temperature",
    )
    assert source.entity_id == SOURCE
    hass.states.async_set(SOURCE, "20.0", {"unit_of_measurement": "°C"})

    _, alarm_id = await _setup_entry(hass, BASE_DATA)

    # The Alarm and both Threshold Entities attach to the same device
    assert registry.async_get(alarm_id).device_id == device.id
    for kind in ("min", "max"):
        threshold_id = registry.async_get_entity_id(
            "number", DOMAIN, threshold_unique_id(SOURCE, kind)
        )
        assert registry.async_get(threshold_id).device_id == device.id
