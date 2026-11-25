"""Read port for spoiler-safe retrieval over the RAG index."""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.retrieval import KnowledgeHit, RetrievedChunk


class RetrievalRepository(Protocol):
    async def search_chunks(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RetrievedChunk]: ...

    async def search_knowledge(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[KnowledgeHit]: ...

    async def expand_entity_chunks(
        self,
        book_id: str,
        position: float,
        canonical_ids: Sequence[str],
        limit: int,
    ) -> list[RetrievedChunk]: ...
