"""Shared database check expressions."""

READING_POSITION_CHECK = "reading_position >= 0.0 AND reading_position <= 1.0"
FIRST_SEEN_POSITION_CHECK = (
    "first_seen_position >= 0.0 AND first_seen_position <= 1.0"
)
