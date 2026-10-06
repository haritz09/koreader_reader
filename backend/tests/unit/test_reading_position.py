import math

import pytest

from core.domain.value_objects.reading_position import (
    InvalidReadingPositionError,
    validate_reading_position,
)


@pytest.mark.parametrize("position", [0.0, 0.5, 1.0])
def test_positions_inside_the_unit_range_are_accepted(position: float) -> None:
    assert validate_reading_position(position) == position


def test_a_position_above_one_is_rejected_rather_than_widening_retrieval() -> None:
    with pytest.raises(InvalidReadingPositionError):
        validate_reading_position(1.0001)


def test_a_negative_position_is_rejected() -> None:
    with pytest.raises(InvalidReadingPositionError):
        validate_reading_position(-0.0001)


def test_a_non_finite_position_is_rejected() -> None:
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(InvalidReadingPositionError):
            validate_reading_position(value)


def test_a_non_numeric_position_is_rejected() -> None:
    for value in ("0.5", None, True):
        with pytest.raises(InvalidReadingPositionError):
            validate_reading_position(value)


def test_an_integer_position_is_accepted_and_narrowed_to_float() -> None:
    value = validate_reading_position(1)

    assert isinstance(value, float)
    assert value == 1.0
