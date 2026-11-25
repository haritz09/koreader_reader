"""Graph retrieval: knowledge hits resolve to visible chunks without duplicates."""

import asyncio

from rag.application.retrieve_graph import RetrieveGraphContextUseCase
from rag.domain.retrieval import KnowledgeHit, RetrievedChunk
from tests.fixtures.embeddings import FakeEmbeddingProvider

MODEL = "test-model"


def chunk(chunk_id: str, reading_position: float, distance: float = 0.1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        chunk_index=0,
        reading_position=reading_position,
        distance=distance,
        text=f"text-{chunk_id}",
    )


class _FakeRepository:
    def __init__(
        self,
        hits: list[KnowledgeHit],
        expanded: list[RetrievedChunk],
    ) -> None:
        self.hits = hits
        self.expanded = expanded
        self.expanded_calls: list[tuple[str, float, tuple[str, ...], int]] = []

    async def search_knowledge(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[KnowledgeHit]:
        return [hit for hit in self.hits if hit.chunk.reading_position <= position]

    async def expand_entity_chunks(
        self,
        book_id: str,
        position: float,
        canonical_ids: tuple[str, ...],
        limit: int,
    ) -> list[RetrievedChunk]:
        self.expanded_calls.append((book_id, position, tuple(canonical_ids), limit))
        return [item for item in self.expanded if item.reading_position <= position]


def test_knowledge_hits_expand_through_identity_and_stay_deduplicated() -> None:
    repository = _FakeRepository(
        hits=[
            KnowledgeHit(chunk("chunk-a", 0.1), "canon-a"),
            KnowledgeHit(chunk("chunk-b", 0.2, 0.3), None),
            KnowledgeHit(chunk("chunk-late", 0.9), "canon-late"),
        ],
        expanded=[chunk("chunk-a", 0.1), chunk("chunk-c", 0.4)],
    )
    use_case = RetrieveGraphContextUseCase(
        repository,
        FakeEmbeddingProvider(model=MODEL),
        top_k=8,
        expansion_limit=4,
    )

    result = asyncio.run(use_case.execute("book", 0.5, "who is here"))

    assert [item.chunk_id for item in result.chunks] == ["chunk-a", "chunk-b", "chunk-c"]
    assert repository.expanded_calls == [("book", 0.5, ("canon-a",), 4)]
    expanded = result.chunks[-1]
    assert expanded.distance == 0.1
    assert all(item.reading_position <= 0.5 for item in result.chunks)
