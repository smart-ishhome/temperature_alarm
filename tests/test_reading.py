"""Tests for Reading extraction (reading.py).

reading.py is deliberately HA-free, so states are stubbed with a
minimal stand-in for homeassistant.core.State.
"""
from types import SimpleNamespace

from reading import reading_of, unit_of


def make_state(state, **attributes):
    return SimpleNamespace(state=state, attributes=attributes)


class TestReadingOf:
    def test_numeric_string(self):
        assert reading_of(make_state("21.5")) == 21.5

    def test_integer_string(self):
        assert reading_of(make_state("21")) == 21.0

    def test_negative(self):
        assert reading_of(make_state("-3.2")) == -3.2

    def test_missing_entity_has_no_reading(self):
        assert reading_of(None) is None

    def test_unavailable_has_no_reading(self):
        assert reading_of(make_state("unavailable")) is None

    def test_unknown_has_no_reading(self):
        assert reading_of(make_state("unknown")) is None

    def test_non_numeric_has_no_reading(self):
        assert reading_of(make_state("warm")) is None

    def test_empty_string_has_no_reading(self):
        assert reading_of(make_state("")) is None

    def test_none_state_value_has_no_reading(self):
        # float(None) raises TypeError, not ValueError - the hole the
        # setup flow's numeric check used to have.
        assert reading_of(make_state(None)) is None


class TestUnitOf:
    def test_unit_present(self):
        assert unit_of(make_state("21", unit_of_measurement="°C")) == "°C"

    def test_no_unit_attribute(self):
        assert unit_of(make_state("21")) is None

    def test_empty_unit_is_no_unit(self):
        assert unit_of(make_state("21", unit_of_measurement="")) is None

    def test_missing_entity_has_no_unit(self):
        assert unit_of(None) is None
