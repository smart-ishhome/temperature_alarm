"""Alarm evaluation for the Temperature Alarm integration.

The Alarm Evaluator owns all alarm semantics: the Monitoring Mode
comparison and the Trigger Delay state machine. It is deliberately free
of Home Assistant imports so it can be tested with plain pytest; the
binary sensor entity is the adapter that resolves the reading and
Thresholds, feeds them in, and applies the resulting Verdict.
"""
from __future__ import annotations

from dataclasses import dataclass

# Monitoring modes. These are the values stored in config entries; the
# rest of the integration imports them via const.py.
MODE_MIN_ONLY = "min_only"
MODE_MAX_ONLY = "max_only"
MODE_MIN_MAX = "min_max"


@dataclass(frozen=True)
class Thresholds:
    """Resolved threshold values, already looked up by the adapter."""

    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Verdict:
    """The outcome of one evaluation - everything the adapter must apply.

    recheck_in asks the adapter to re-evaluate after that many seconds;
    it is set only on the evaluation that starts a pending delay. When
    pending is False any previously requested re-check is obsolete.
    """

    available: bool
    is_on: bool | None
    pending: bool
    pending_updates: int
    recheck_in: float | None = None


_UNAVAILABLE = Verdict(
    available=False, is_on=None, pending=False, pending_updates=0
)


class AlarmEvaluator:
    """Evaluates alarm state for one Temperature Alarm.

    Holds the Trigger Delay tracking state between evaluations. The
    clock is injected through ``now`` (monotonic seconds), so behaviour
    is fully deterministic under test.
    """

    def __init__(
        self,
        mode: str,
        delay_enabled: bool,
        delay_time: float,
        delay_updates: int,
    ) -> None:
        """Initialize the evaluator with the alarm's configuration."""
        self._mode = mode
        self._delay_enabled = delay_enabled
        self._delay_time = delay_time
        self._delay_updates = delay_updates
        self._pending_since: float | None = None
        self._update_count = 0

    def evaluate(
        self, reading: float | None, thresholds: Thresholds, now: float
    ) -> Verdict:
        """Evaluate the alarm given the current reading and Thresholds.

        ``reading`` is None when the Source Sensor is unavailable or not
        numeric; that resets any pending delay.
        """
        if reading is None:
            self._reset()
            return _UNAVAILABLE

        condition = self._condition_met(reading, thresholds)

        if self._delay_enabled and condition:
            return self._apply_delay(now)

        self._reset()
        return self._verdict(is_on=condition)

    def _condition_met(self, reading: float, thresholds: Thresholds) -> bool:
        """Check the reading against the Thresholds for this mode."""
        if self._mode == MODE_MIN_ONLY:
            return thresholds.min is not None and reading < thresholds.min
        if self._mode == MODE_MAX_ONLY:
            return thresholds.max is not None and reading > thresholds.max
        if self._mode == MODE_MIN_MAX:
            if thresholds.min is not None and reading < thresholds.min:
                return True
            return thresholds.max is not None and reading > thresholds.max
        return False

    def _apply_delay(self, now: float) -> Verdict:
        """Run the Trigger Delay state machine for a met condition.

        The alarm turns on once EITHER the elapsed time reaches
        delay_time OR the number of evaluations reaches delay_updates.
        Tracking is not reset when the alarm triggers; it clears when
        the condition stops being met or the reading goes unavailable.
        """
        recheck_in: float | None = None
        if self._pending_since is None:
            self._pending_since = now
            self._update_count = 0
            recheck_in = self._delay_time

        self._update_count += 1

        elapsed = now - self._pending_since
        time_met = elapsed >= self._delay_time
        updates_met = self._update_count >= self._delay_updates

        return self._verdict(is_on=time_met or updates_met, recheck_in=recheck_in)

    def _reset(self) -> None:
        """Clear Trigger Delay tracking."""
        self._pending_since = None
        self._update_count = 0

    def _verdict(
        self, is_on: bool, recheck_in: float | None = None
    ) -> Verdict:
        pending = self._pending_since is not None
        return Verdict(
            available=True,
            is_on=is_on,
            pending=pending,
            pending_updates=self._update_count if pending else 0,
            recheck_in=recheck_in,
        )
