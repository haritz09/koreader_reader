"""Chat answer types shared by the use case, adapters, and HTTP layer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnswerDraft:
    text: str
    cited_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChatSource:
    chunk_id: str
    chunk_index: int
    reading_position: float
    distance: float
    excerpt: str


@dataclass(frozen=True)
class ChatAnswer:
    book_id: str
    position: float
    model: str
    answer: str
    sources: tuple[ChatSource, ...]
