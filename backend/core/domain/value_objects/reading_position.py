"""Validated reading position value object."""

import math
from dataclasses import dataclass


class InvalidReadingPositionError(ValueError):
    """Raised when a reading position falls outside the inclusive unit range."""


@dataclass(frozen=True)
class ReadingPosition:
    """A reading position constrained to the inclusive range [0.0, 1.0].

    Spoiler filtering compares stored knowledge positions against the reader's
    current position, so a value above 1.0 would widen retrieval to the whole
    book and a non-finite value would silently match nothing. Both are spoiler
    risks, so the range is enforced here rather than trusted from the caller.
    """

    value: float

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise InvalidReadingPositionError(
                f"Reading position must be a number, got {self.value!r}"
            )
        if not math.isfinite(self.value):
            raise InvalidReadingPositionError(
                f"Reading position must be finite, got {self.value!r}"
            )
        if not 0.0 <= self.value <= 1.0:
            raise InvalidReadingPositionError(
                f"Reading position must be within [0.0, 1.0], got {self.value!r}"
            )

    def __float__(self) -> float:
        return float(self.value)


def validate_reading_position(value: float) -> float:
    """Return the value as a float, raising when it cannot be a valid position."""
    return float(ReadingPosition(value))
