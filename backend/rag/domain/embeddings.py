"""Embedding domain types shared by the pipeline and its persistence adapter."""

from dataclasses import dataclass
from enum import StrEnum

EMBEDDING_DIMENSIONS = 768


class EmbeddingSourceType(StrEnum):
    CHUNK = "chunk"
    ENTITY = "entity"
    FACT = "fact"
    EVENT = "event"
    LOCATION = "location"


EMBEDDING_SOURCE_TYPES: tuple[EmbeddingSourceType, ...] = tuple(EmbeddingSourceType)

EMBEDDING_SOURCE_TYPE_VALUES = ", ".join(
    f"'{source_type.value}'" for source_type in EMBEDDING_SOURCE_TYPES
)


@dataclass(frozen=True)
class EmbeddingSource:
    source_type: EmbeddingSourceType
    source_id: str
    chunk_id: str | None
    reading_position: float
    text: str


@dataclass(frozen=True)
class EmbeddingSummary:
    total: int
    embedded: int
    reused: int
