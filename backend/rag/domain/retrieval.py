"""Retrieval types shared by the read path and its persistence adapter."""

from dataclasses import dataclass
from enum import StrEnum


class RetrievalStrategy(StrEnum):
    RAG = "rag"
    GRAPH = "graph"


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


@dataclass(frozen=True)
class KnowledgeHit:
    chunk: RetrievedChunk
    canonical_id: str | None
