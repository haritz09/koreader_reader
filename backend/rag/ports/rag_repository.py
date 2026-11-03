"""Persistence port for embeddings and community indexes."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from rag.domain.clustering import ClusterGraph, ClusterSources, CommunityTree
from rag.domain.embeddings import EmbeddingSource
from rag.domain.status import RagIndexStatus


class RagRepository(Protocol):
    async def get_graph_revision(self, book_id: str) -> int: ...

    async def get_embedding_sources(self, book_id: str) -> list[EmbeddingSource]: ...

    async def get_existing_hashes(
        self,
        book_id: str,
        model: str,
    ) -> Mapping[tuple[str, str], str]: ...

    async def upsert_embeddings(
        self,
        book_id: str,
        model: str,
        rows: Sequence[tuple[EmbeddingSource, str, list[float]]],
    ) -> None: ...

    async def get_cluster_sources(self, book_id: str) -> ClusterSources: ...

    async def save_community_run(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        graph: ClusterGraph,
        tree: CommunityTree,
        status: RagIndexStatus,
        error: str | None = None,
    ) -> str: ...

    async def claim_build(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        stale_after_seconds: int,
    ) -> bool: ...

    async def mark_pending(self, book_id: str, error: str | None = None) -> None: ...

    async def mark_failed(self, book_id: str, error: str) -> None: ...

    async def needs_build(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        stale_after_seconds: int,
    ) -> bool: ...

    async def delete_by_book(self, book_id: str) -> None: ...
