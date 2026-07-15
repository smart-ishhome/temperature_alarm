"""Reading extraction for the Temperature Alarm integration.

Owns the rule for what a watched entity's state yields: the Reading (a
live numeric value - normally the Source Sensor's temperature, but
Threshold Entities yield Readings the same way) and the unit of
measurement. Deliberately free of Home Assistant imports so it can be
tested with plain pytest.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import State

# homeassistant.const STATE_UNAVAILABLE / STATE_UNKNOWN, spelled out to
# keep this module importable without Home Assistant.
_NO_READING_STATES = ("unavailable", "unknown")


def reading_of(state: State | None) -> float | None:
    """The entity's current Reading, or None if it has none.

    A Reading is absent when the entity is missing, unavailable,
    unknown, or its state is non-numeric.
    """
    if state is None or state.state in _NO_READING_STATES:
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


def unit_of(state: State | None) -> str | None:
    """The entity's unit of measurement, or None if it has none."""
    if state is None:
        return None
    return state.attributes.get("unit_of_measurement") or None
