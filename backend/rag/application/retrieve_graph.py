"""Retrieve spoiler-safe context from the graph's knowledge embeddings."""

from dataclasses import replace

from core.domain.value_objects.reading_position import validate_reading_position
from rag.domain.errors import EmbeddingConfigurationError
from rag.domain.retrieval import KnowledgeHit, RetrievalResult, RetrievedChunk
from rag.ports.embedding_provider import EmbeddingProvider
from rag.ports.retrieval_repository import RetrievalRepository


class RetrieveGraphContextUseCase:
    def __init__(
        self,
        repository: RetrievalRepository,
        embeddings: EmbeddingProvider,
        *,
        top_k: int,
        expansion_limit: int,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._top_k = max(1, top_k)
        self._expansion_limit = max(0, expansion_limit)

    async def execute(
        self,
        book_id: str,
        position: float,
        question: str,
    ) -> RetrievalResult:
        position_value = validate_reading_position(position)
        text = question.strip()
        if not text:
            raise ValueError("Question must not be blank")

        query_embedding = await self._embeddings.embed_query(text)
        if len(query_embedding) != self._embeddings.dimensions:
            raise EmbeddingConfigurationError(
                f"Query embedding has {len(query_embedding)} dimensions, "
                f"expected {self._embeddings.dimensions}"
            )

        hits = await self._repository.search_knowledge(
            book_id,
            position_value,
            self._embeddings.model,
            query_embedding,
            self._top_k,
        )
        chunks = [hit.chunk for hit in hits if hit.chunk.reading_position <= position_value]
        chunks.extend(await self._expand(book_id, position_value, hits, chunks))
        return RetrievalResult(
            book_id=book_id,
            position=position_value,
            model=self._embeddings.model,
            chunks=tuple(_unique_by_chunk_id(chunks)),
        )

    async def _expand(
        self,
        book_id: str,
        position: float,
        hits: list[KnowledgeHit],
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        canonical_ids = tuple({hit.canonical_id for hit in hits if hit.canonical_id})
        if not canonical_ids or self._expansion_limit == 0:
            return []
        expanded = await self._repository.expand_entity_chunks(
            book_id,
            position,
            canonical_ids,
            self._expansion_limit,
        )
        floor = min((chunk.distance for chunk in chunks), default=1.0)
        return [replace(chunk, distance=floor) for chunk in expanded]


def _unique_by_chunk_id(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: dict[str, RetrievedChunk] = {}
    for chunk in chunks:
        seen.setdefault(chunk.chunk_id, chunk)
    return list(seen.values())
