"""Incremental embedding generation and retry behavior."""

import asyncio

import pytest

from rag.application.embeddings import EmbedKnowledgeService, content_hash
from rag.domain.embeddings import EmbeddingSource, EmbeddingSourceType
from rag.domain.errors import EmbeddingError, EmbeddingTransientError


class FakeRepository:
    def __init__(
        self,
        sources: list[EmbeddingSource],
        existing: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self.sources = sources
        self.existing = existing or {}
        self.rows: list[tuple[EmbeddingSource, str, list[float]]] = []

    async def get_embedding_sources(self, book_id: str) -> list[EmbeddingSource]:
        return list(self.sources)

    async def get_existing_hashes(self, book_id: str, model: str):
        return dict(self.existing)

    async def upsert_embeddings(self, book_id, model, dimensions, rows) -> None:
        self.rows.extend(rows)


class FakeProvider:
    model = "test-embedding"
    dimensions = 2

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[list[str]] = []

    async def embed_documents(self, texts):
        self.calls.append(list(texts))
        if self.failures:
            self.failures -= 1
            raise EmbeddingTransientError("temporary")
        return [[1.0, 0.0] for _ in texts]


def source(source_type: EmbeddingSourceType, source_id: str, text: str) -> EmbeddingSource:
    return EmbeddingSource(
        source_type=source_type,
        source_id=source_id,
        chunk_id=f"chunk-{source_id}",
        reading_position=0.25,
        text=text,
    )


def service(repository: FakeRepository, provider: FakeProvider, **overrides):
    options = {
        "dimensions": 2,
        "batch_size": 2,
        "max_attempts": 2,
        "retry_base_seconds": 0.0,
        "retry_max_seconds": 0.0,
    }
    options.update(overrides)
    return EmbedKnowledgeService(provider, repository, **options)


def test_only_new_or_changed_sources_are_embedded() -> None:
    unchanged = source(EmbeddingSourceType.CHUNK, "c1", "same text")
    repository = FakeRepository(
        [
            unchanged,
            source(EmbeddingSourceType.FACT, "f1", "new fact"),
            source(EmbeddingSourceType.ENTITY, "e1", "new entity"),
        ],
        existing={(EmbeddingSourceType.CHUNK.value, "c1"): content_hash("same text")},
    )
    provider = FakeProvider()

    summary = asyncio.run(service(repository, provider).embed_book("book-1"))

    assert summary.total == 3
    assert summary.embedded == 2
    assert summary.reused == 1
    assert provider.calls == [["new fact", "new entity"]]
    assert {row[0].source_id for row in repository.rows} == {"f1", "e1"}


def test_transient_failure_is_retried() -> None:
    repository = FakeRepository([source(EmbeddingSourceType.CHUNK, "c1", "text")])
    provider = FakeProvider(failures=1)

    summary = asyncio.run(service(repository, provider).embed_book("book-1"))

    assert summary.embedded == 1
    assert len(provider.calls) == 2


def test_invalid_vector_count_raises() -> None:
    class BrokenProvider(FakeProvider):
        async def embed_documents(self, texts):
            return [[1.0, 0.0]]

    repository = FakeRepository(
        [
            source(EmbeddingSourceType.CHUNK, "c1", "one"),
            source(EmbeddingSourceType.CHUNK, "c2", "two"),
        ]
    )

    with pytest.raises(EmbeddingError, match="incomplete batch"):
        asyncio.run(
            service(repository, BrokenProvider(), max_attempts=1).embed_book("book-1")
        )
