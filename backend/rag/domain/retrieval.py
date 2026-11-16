"""Retrieval types shared by the read path and its persistence adapter."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    chunk_index: int
    reading_position: float
    distance: float
    text: str


@dataclass(frozen=True)
class RetrievalResult:
    book_id: str
    position: float
    model: str
    chunks: tuple[RetrievedChunk, ...]
