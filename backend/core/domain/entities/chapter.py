"""Chapter domain entity."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
	chapter_id: str
	title: str
	text: str
	chapter_index: int
