"""Queue port for RAG index builds."""

from typing import Protocol


class RagIndexQueue(Protocol):
    async def enqueue(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
    ) -> None: ...
