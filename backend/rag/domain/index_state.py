"""Read model for a book's RAG index state."""

from dataclasses import dataclass

from rag.domain.status import RagIndexStatus


@dataclass(frozen=True)
class RagIndexState:
    status: RagIndexStatus
    embedding_model: str
