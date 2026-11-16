"""Retrieval use case: spoiler filtering at the application boundary."""

import asyncio
from collections.abc import Sequence

import pytest

from core.domain.value_objects.reading_position import InvalidReadingPositionError
from rag.application.retrieve import RetrieveContextUseCase
from rag.domain.errors import EmbeddingConfigurationError
from rag.domain.retrieval import RetrievedChunk


def chunk(
    chunk_id: str,
    reading_position: float,
    distance: float = 0.1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        chunk_index=0,
        reading_position=reading_position,
        distance=distance,
        text=f"text-{chunk_id}",
    )


class _FakeEmbeddingProvider:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = [0.1, 0.2, 0.3] if vector is None else vector
        self.queries: list[str] = []

    @property
    def model(self) -> str:
        return "test-model"

    @property
    def dimensions(self) -> int:
        return 3

    @property
    def max_batch_size(self) -> int:
        return 100

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("retrieval must not embed documents")

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self.vector


class _FakeRetrievalRepository:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[str, float, str, list[float], int]] = []

    async def search_chunks(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        self.calls.append(
            (book_id, position, model, list(query_embedding), limit)
        )
        return list(self.chunks)


def build_use_case(
    chunks: list[RetrievedChunk],
    provider: _FakeEmbeddingProvider | None = None,
) -> tuple[RetrieveContextUseCase, _FakeRetrievalRepository, _FakeEmbeddingProvider]:
    repository = _FakeRetrievalRepository(chunks)
    embeddings = provider or _FakeEmbeddingProvider()
    use_case = RetrieveContextUseCase(repository, embeddings, top_k=3)
    return use_case, repository, embeddings


def test_returns_only_chunks_visible_at_the_position() -> None:
    use_case, _, _ = build_use_case(
        [chunk("early", 0.1), chunk("boundary", 0.5), chunk("late", 0.9)]
    )

    result = asyncio.run(use_case.execute("book", 0.5, "who betrayed Jon"))

    assert [item.chunk_id for item in result.chunks] == ["early", "boundary"]


def test_boundary_position_is_inclusive() -> None:
    use_case, _, _ = build_use_case([chunk("exact", 0.5)])

    result = asyncio.run(use_case.execute("book", 0.5, "question"))

    assert [item.chunk_id for item in result.chunks] == ["exact"]


def test_blank_question_is_rejected_without_embedding() -> None:
    use_case, repository, embeddings = build_use_case([chunk("early", 0.1)])

    with pytest.raises(ValueError):
        asyncio.run(use_case.execute("book", 0.5, "   "))

    assert embeddings.queries == []
    assert repository.calls == []


@pytest.mark.parametrize("position", [float("nan"), -0.1, 1.1])
def test_invalid_position_is_rejected_without_embedding(position: float) -> None:
    use_case, repository, embeddings = build_use_case([chunk("early", 0.1)])

    with pytest.raises(InvalidReadingPositionError):
        asyncio.run(use_case.execute("book", position, "question"))

    assert embeddings.queries == []
    assert repository.calls == []


def test_passes_provider_model_and_top_k_to_the_repository() -> None:
    use_case, repository, _ = build_use_case([chunk("early", 0.1)])

    asyncio.run(use_case.execute("book", 0.5, " question "))

    assert repository.calls == [("book", 0.5, "test-model", [0.1, 0.2, 0.3], 3)]


def test_explicit_limit_overrides_top_k() -> None:
    use_case, repository, _ = build_use_case([chunk("early", 0.1)])

    asyncio.run(use_case.execute("book", 0.5, "question", limit=1))

    assert repository.calls[0][4] == 1


def test_embedding_dimension_mismatch_is_rejected_before_querying() -> None:
    provider = _FakeEmbeddingProvider(vector=[0.1, 0.2])
    use_case, repository, _ = build_use_case([chunk("early", 0.1)], provider)

    with pytest.raises(EmbeddingConfigurationError):
        asyncio.run(use_case.execute("book", 0.5, "question"))

    assert repository.calls == []


def test_empty_index_returns_no_chunks() -> None:
    use_case, _, _ = build_use_case([])

    result = asyncio.run(use_case.execute("book", 0.5, "question"))

    assert result.chunks == ()
    assert result.position == 0.5
    assert result.model == "test-model"
