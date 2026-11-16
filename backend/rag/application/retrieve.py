"""Retrieve spoiler-safe context for a question."""

from core.domain.value_objects.reading_position import validate_reading_position
from rag.domain.errors import EmbeddingConfigurationError
from rag.domain.retrieval import RetrievalResult
from rag.ports.embedding_provider import EmbeddingProvider
from rag.ports.retrieval_repository import RetrievalRepository


class RetrieveContextUseCase:
    def __init__(
        self,
        repository: RetrievalRepository,
        embeddings: EmbeddingProvider,
        *,
        top_k: int,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._top_k = max(1, top_k)

    async def execute(
        self,
        book_id: str,
        position: float,
        question: str,
        limit: int | None = None,
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

        chunks = await self._repository.search_chunks(
            book_id,
            position_value,
            self._embeddings.model,
            query_embedding,
            self._top_k if limit is None else limit,
        )
        return RetrievalResult(
            book_id=book_id,
            position=position_value,
            model=self._embeddings.model,
            chunks=tuple(
                chunk for chunk in chunks if chunk.reading_position <= position_value
            ),
        )
