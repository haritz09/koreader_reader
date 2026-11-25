"""Port for the two spoiler-safe context strategies chat can use."""

from typing import Protocol

from rag.domain.retrieval import RetrievalResult


class ContextRetriever(Protocol):
    async def execute(
        self,
        book_id: str,
        position: float,
        question: str,
    ) -> RetrievalResult: ...
