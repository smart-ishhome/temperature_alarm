"""Threshold Resolution for the Temperature Alarm integration.

Owns everything about Thresholds except alarm semantics: which
Threshold Entities should exist for an alarm, their unique IDs, the
current resolved values (Threshold Entity first, config fallback), and
change notification. Consumers never learn where a Threshold came from.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_CREATE_MAX_ENTITY,
    CONF_CREATE_MIN_ENTITY,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
)
from .evaluator import Thresholds
from .reading import reading_of

_LOGGER = logging.getLogger(__name__)

KINDS = ("min", "max")

_MODES_WITH = {
    "min": (MODE_MIN_ONLY, MODE_MIN_MAX),
    "max": (MODE_MAX_ONLY, MODE_MIN_MAX),
}
_CREATE_FLAG = {"min": CONF_CREATE_MIN_ENTITY, "max": CONF_CREATE_MAX_ENTITY}
_CONFIG_KEY = {"min": CONF_MIN_TEMP, "max": CONF_MAX_TEMP}


def wants_entity(data: Mapping[str, Any], kind: str) -> bool:
    """Whether a Threshold Entity of this kind should exist for the entry."""
    mode = data.get(CONF_MODE, MODE_MIN_MAX)
    return mode in _MODES_WITH[kind] and data.get(_CREATE_FLAG[kind], True)


def threshold_unique_id(source_entity_id: str, kind: str) -> str:
    """Unique ID of a Threshold Entity.

    The format is persisted in the entity registry; changing it orphans
    existing entities.
    """
    return f"{DOMAIN}_{source_entity_id}_{kind}_temperature"


class ThresholdResolver:
    """Resolves the current Thresholds and notifies on changes.

    Values come from the Threshold Entity's state when one exists and
    yields a Reading, otherwise from the config entry.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

    def current(self) -> Thresholds:
        """Resolve the current Thresholds."""
        return Thresholds(min=self._value("min"), max=self._value("max"))

    def async_subscribe(self, on_change: Callable[[], None]) -> CALLBACK_TYPE:
        """Call on_change whenever a Threshold Entity's state changes.

        Returns an unsubscribe callback. Threshold Entities are looked
        up once, at subscribe time.
        """
        entity_ids = [
            entity_id
            for kind in KINDS
            if (entity_id := self._entity_id(kind)) is not None
        ]
        if not entity_ids:
            return lambda: None

        @callback
        def _changed(_event: Event) -> None:
            on_change()

        return async_track_state_change_event(self._hass, entity_ids, _changed)

    def _entity_id(self, kind: str) -> str | None:
        source_entity_id = self._entry.data[CONF_SOURCE_ENTITY]
        return er.async_get(self._hass).async_get_entity_id(
            "number", DOMAIN, threshold_unique_id(source_entity_id, kind)
        )

    def _value(self, kind: str) -> float | None:
        entity_id = self._entity_id(kind)
        if entity_id is not None:
            state = self._hass.states.get(entity_id)
            reading = reading_of(state)
            if reading is not None:
                return reading
            if state is not None:
                _LOGGER.debug(
                    "No Reading from %s Threshold Entity (state: %r), using config",
                    kind,
                    state.state,
                )
        return self._entry.data.get(_CONFIG_KEY[kind])
