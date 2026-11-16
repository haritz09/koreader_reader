"""Read port for the state of a book's RAG index."""

from typing import Protocol

from rag.domain.index_state import RagIndexState


class RagIndexReader(Protocol):
    async def get_index_state(self, book_id: str) -> RagIndexState | None: ...
