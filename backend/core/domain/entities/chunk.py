"""Chunk domain entity."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
	chapter_id: str
	chunk_index: int
	text: str
	start_pctg: float
	end_pctg: float
