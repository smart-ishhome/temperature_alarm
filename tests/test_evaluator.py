"""Characterization tests for the Alarm Evaluator.

These pin the behaviour extracted from the binary sensor entity
(pre-extraction: binary_sensor.py _update_state and _handle_delay_logic),
with one deliberate correction: the Trigger Delay update counter advances
only on Source Sensor updates (see TestDelayUpdatesCriterion). Tests
marked QUIRK document behaviour that is pinned as intended.
"""
from evaluator import (
    MODE_MAX_ONLY,
    MODE_MIN_MAX,
    MODE_MIN_ONLY,
    AlarmEvaluator,
    Thresholds,
    Trigger,
)


def make_evaluator(
    mode: str = MODE_MIN_MAX,
    delay_enabled: bool = False,
    delay_time: float = 300,
    delay_updates: int = 3,
) -> AlarmEvaluator:
    return AlarmEvaluator(
        mode=mode,
        delay_enabled=delay_enabled,
        delay_time=delay_time,
        delay_updates=delay_updates,
    )


BOTH = Thresholds(min=10.0, max=30.0)


class TestModeComparison:
    def test_min_only_below_threshold_is_on(self):
        v = make_evaluator(MODE_MIN_ONLY).evaluate(5.0, BOTH, now=0)
        assert v.is_on is True

    def test_min_only_at_threshold_is_off(self):
        # Comparison is strict: reading == min is not an alarm.
        v = make_evaluator(MODE_MIN_ONLY).evaluate(10.0, BOTH, now=0)
        assert v.is_on is False

    def test_min_only_ignores_max_threshold(self):
        v = make_evaluator(MODE_MIN_ONLY).evaluate(99.0, BOTH, now=0)
        assert v.is_on is False

    def test_min_only_without_min_threshold_is_off(self):
        v = make_evaluator(MODE_MIN_ONLY).evaluate(5.0, Thresholds(), now=0)
        assert v.is_on is False

    def test_max_only_above_threshold_is_on(self):
        v = make_evaluator(MODE_MAX_ONLY).evaluate(35.0, BOTH, now=0)
        assert v.is_on is True

    def test_max_only_at_threshold_is_off(self):
        v = make_evaluator(MODE_MAX_ONLY).evaluate(30.0, BOTH, now=0)
        assert v.is_on is False

    def test_max_only_ignores_min_threshold(self):
        v = make_evaluator(MODE_MAX_ONLY).evaluate(5.0, BOTH, now=0)
        assert v.is_on is False

    def test_min_max_inside_range_is_off(self):
        v = make_evaluator(MODE_MIN_MAX).evaluate(20.0, BOTH, now=0)
        assert v.is_on is False

    def test_min_max_below_range_is_on(self):
        v = make_evaluator(MODE_MIN_MAX).evaluate(5.0, BOTH, now=0)
        assert v.is_on is True

    def test_min_max_above_range_is_on(self):
        v = make_evaluator(MODE_MIN_MAX).evaluate(35.0, BOTH, now=0)
        assert v.is_on is True

    def test_min_max_with_only_min_resolved_still_alarms_low(self):
        v = make_evaluator(MODE_MIN_MAX).evaluate(
            5.0, Thresholds(min=10.0), now=0
        )
        assert v.is_on is True

    def test_unknown_mode_is_off(self):
        v = make_evaluator("bogus").evaluate(5.0, BOTH, now=0)
        assert v.is_on is False


class TestAvailability:
    def test_no_reading_is_unavailable(self):
        v = make_evaluator().evaluate(None, BOTH, now=0)
        assert v.available is False
        assert v.is_on is None
        assert v.pending is False
        assert v.pending_updates == 0

    def test_valid_reading_is_available(self):
        v = make_evaluator().evaluate(20.0, BOTH, now=0)
        assert v.available is True

    def test_unavailable_resets_pending_delay(self):
        # QUIRK 3 (pinned as intended): a Source Sensor dropout restarts
        # the Trigger Delay from scratch - the temperature may have
        # recovered while the sensor was dark.
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        ev.evaluate(5.0, BOTH, now=0)
        ev.evaluate(None, BOTH, now=100)
        v = ev.evaluate(5.0, BOTH, now=200)
        assert v.is_on is False
        assert v.pending is True
        assert v.pending_updates == 1  # counter restarted
        assert v.recheck_in == 300  # timer restarted too


class TestDelayDisabled:
    def test_alarm_is_immediate(self):
        v = make_evaluator(delay_enabled=False).evaluate(5.0, BOTH, now=0)
        assert v.is_on is True
        assert v.pending is False
        assert v.recheck_in is None

    def test_recovery_is_immediate(self):
        ev = make_evaluator(delay_enabled=False)
        ev.evaluate(5.0, BOTH, now=0)
        v = ev.evaluate(20.0, BOTH, now=1)
        assert v.is_on is False


class TestDelayTimeCriterion:
    def test_first_evaluation_starts_pending_and_requests_recheck(self):
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        v = ev.evaluate(5.0, BOTH, now=1000)
        assert v.is_on is False
        assert v.pending is True
        assert v.pending_updates == 1
        assert v.recheck_in == 300

    def test_recheck_requested_only_when_pending_starts(self):
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        ev.evaluate(5.0, BOTH, now=1000)
        v = ev.evaluate(5.0, BOTH, now=1100)
        assert v.recheck_in is None

    def test_alarm_on_once_delay_time_elapses(self):
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        ev.evaluate(5.0, BOTH, now=1000)
        assert ev.evaluate(5.0, BOTH, now=1299).is_on is False
        assert ev.evaluate(5.0, BOTH, now=1300).is_on is True

    def test_pending_persists_after_alarm_triggers(self):
        # Pinned: triggering does NOT clear delay tracking - the alarm
        # keeps reporting alarm_pending until the condition clears.
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        ev.evaluate(5.0, BOTH, now=1000)
        v = ev.evaluate(5.0, BOTH, now=1300)
        assert v.is_on is True
        assert v.pending is True

    def test_zero_delay_time_triggers_immediately(self):
        ev = make_evaluator(delay_enabled=True, delay_time=0, delay_updates=99)
        assert ev.evaluate(5.0, BOTH, now=1000).is_on is True

    def test_pending_restart_requests_recheck_again(self):
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        ev.evaluate(5.0, BOTH, now=0)
        ev.evaluate(20.0, BOTH, now=10)  # recovered - resets tracking
        v = ev.evaluate(5.0, BOTH, now=20)
        assert v.recheck_in == 300


class TestDelayUpdatesCriterion:
    # The counter counts Source Sensor updates observed while the
    # condition holds (including the one that entered it). Threshold
    # changes and timer re-checks re-evaluate but do not advance it.

    def test_alarm_on_once_source_update_count_reached(self):
        ev = make_evaluator(delay_enabled=True, delay_time=9999, delay_updates=3)
        assert ev.evaluate(5.0, BOTH, now=0).pending_updates == 1
        assert ev.evaluate(5.0, BOTH, now=1).is_on is False
        v = ev.evaluate(5.0, BOTH, now=2)
        assert v.is_on is True
        assert v.pending_updates == 3

    def test_threshold_changes_do_not_advance_the_counter(self):
        ev = make_evaluator(delay_enabled=True, delay_time=9999, delay_updates=2)
        ev.evaluate(5.0, BOTH, now=0)  # source update: count 1
        v = ev.evaluate(5.0, BOTH, now=1, trigger=Trigger.THRESHOLD_CHANGE)
        assert v.is_on is False
        assert v.pending_updates == 1
        assert ev.evaluate(5.0, BOTH, now=2).is_on is True  # 2nd source update

    def test_rechecks_do_not_advance_the_counter(self):
        ev = make_evaluator(delay_enabled=True, delay_time=9999, delay_updates=2)
        ev.evaluate(5.0, BOTH, now=0)
        v = ev.evaluate(5.0, BOTH, now=1, trigger=Trigger.RECHECK)
        assert v.is_on is False
        assert v.pending_updates == 1

    def test_recheck_still_triggers_via_elapsed_time(self):
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        ev.evaluate(5.0, BOTH, now=0)
        v = ev.evaluate(5.0, BOTH, now=300, trigger=Trigger.RECHECK)
        assert v.is_on is True

    def test_pending_can_start_via_threshold_change_with_zero_updates(self):
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=1)
        v = ev.evaluate(5.0, BOTH, now=0, trigger=Trigger.THRESHOLD_CHANGE)
        assert v.is_on is False
        assert v.pending is True
        assert v.pending_updates == 0
        assert v.recheck_in == 300

    def test_single_update_threshold_triggers_immediately(self):
        ev = make_evaluator(delay_enabled=True, delay_time=9999, delay_updates=1)
        assert ev.evaluate(5.0, BOTH, now=0).is_on is True


class TestDelayRecovery:
    def test_recovery_is_immediate_even_with_delay(self):
        # QUIRK 2 (pinned as intended): the Trigger Delay debounces only
        # the on-transition; recovery to off is instant.
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=3)
        ev.evaluate(5.0, BOTH, now=0)
        ev.evaluate(5.0, BOTH, now=1)
        ev.evaluate(5.0, BOTH, now=2)  # triggered via update count
        v = ev.evaluate(20.0, BOTH, now=3)
        assert v.is_on is False
        assert v.pending is False
        assert v.pending_updates == 0

    def test_recovery_while_pending_clears_tracking(self):
        ev = make_evaluator(delay_enabled=True, delay_time=300, delay_updates=99)
        ev.evaluate(5.0, BOTH, now=0)
        v = ev.evaluate(20.0, BOTH, now=10)
        assert v.is_on is False
        assert v.pending is False
