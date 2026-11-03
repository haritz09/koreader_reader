"""Incremental embedding generation and retry behavior."""

import asyncio

import pytest

from rag.application.embeddings import EmbedKnowledgeService, content_hash
from rag.domain.embeddings import EmbeddingSource, EmbeddingSourceType
from rag.domain.errors import (
    EmbeddingError,
    EmbeddingQuotaExhaustedError,
    EmbeddingTransientError,
)


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

    async def upsert_embeddings(self, book_id, model, rows) -> None:
        self.rows.extend(rows)


class FakeProvider:
    model = "test-embedding"
    dimensions = 2
    max_batch_size = 2

    def __init__(self, failures: int = 0, quota_failures: int = 0) -> None:
        self.failures = failures
        self.quota_failures = quota_failures
        self.calls: list[list[str]] = []

    async def embed_documents(self, texts):
        self.calls.append(list(texts))
        if self.quota_failures:
            self.quota_failures -= 1
            raise EmbeddingQuotaExhaustedError("daily quota")
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


def test_identical_texts_are_embedded_once() -> None:
    repository = FakeRepository(
        [
            source(EmbeddingSourceType.ENTITY, "e1", "Alice (character)"),
            source(EmbeddingSourceType.ENTITY, "e2", "Alice (character)"),
            source(EmbeddingSourceType.FACT, "f1", "Alice meets Bob"),
        ]
    )
    provider = FakeProvider()

    summary = asyncio.run(service(repository, provider).embed_book("book-1"))

    assert provider.calls == [["Alice (character)", "Alice meets Bob"]]
    assert summary.embedded == 3
    assert len(repository.rows) == 3
    alice_vectors = {
        tuple(row[2]) for row in repository.rows if row[0].source_id in {"e1", "e2"}
    }
    assert len(alice_vectors) == 1
    assert {row[0].source_id for row in repository.rows} == {"e1", "e2", "f1"}


def test_blank_texts_are_not_sent_to_the_provider() -> None:
    repository = FakeRepository(
        [
            source(EmbeddingSourceType.ENTITY, "e1", "   "),
            source(EmbeddingSourceType.FACT, "f1", "Alice meets Bob"),
        ]
    )
    provider = FakeProvider()

    summary = asyncio.run(service(repository, provider).embed_book("book-1"))

    assert provider.calls == [["Alice meets Bob"]]
    assert summary.embedded == 1
    assert summary.skipped == 1
    assert [row[0].source_id for row in repository.rows] == ["f1"]


def test_daily_quota_is_not_retried() -> None:
    repository = FakeRepository([source(EmbeddingSourceType.CHUNK, "c1", "text")])
    provider = FakeProvider(quota_failures=5)

    with pytest.raises(EmbeddingQuotaExhaustedError):
        asyncio.run(
            service(repository, provider, max_attempts=3).embed_book("book-1")
        )

    assert len(provider.calls) == 1


def test_batch_size_is_capped_by_the_provider() -> None:
    class SingleTextProvider(FakeProvider):
        max_batch_size = 1

    repository = FakeRepository(
        [
            source(EmbeddingSourceType.CHUNK, "c1", "one"),
            source(EmbeddingSourceType.CHUNK, "c2", "two"),
        ]
    )
    provider = SingleTextProvider()

    asyncio.run(service(repository, provider, batch_size=100).embed_book("book-1"))

    assert provider.calls == [["one"], ["two"]]
