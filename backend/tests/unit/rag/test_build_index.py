"""Failure handling for a single RAG index build."""

import asyncio

import pytest

from rag.application.build_index import BuildRagIndexUseCase
from rag.domain.errors import (
    EmbeddingConfigurationError,
    EmbeddingPermanentError,
    EmbeddingQuotaExhaustedError,
    EmbeddingTransientError,
    RagBuildDeferred,
)


class FakeRepository:
    def __init__(self, claimed: bool = True) -> None:
        self.claimed = claimed
        self.pending: list[tuple[str, str | None]] = []
        self.failed: list[tuple[str, str]] = []
        self.claims: list[tuple[str, int, str, int]] = []

    async def claim_build(self, book_id, graph_revision, embedding_model, stale) -> bool:
        self.claims.append((book_id, graph_revision, embedding_model, stale))
        return self.claimed

    async def mark_pending(self, book_id, error=None) -> None:
        self.pending.append((book_id, error))

    async def mark_failed(self, book_id, error) -> None:
        self.failed.append((book_id, error))


class FakeEmbeddings:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.called = False

    async def embed_book(self, book_id):
        self.called = True
        if self.error is not None:
            raise self.error
        return None


class FakeCommunities:
    async def build(self, book_id, graph_revision, embedding_model):
        return None


def use_case(repository, embeddings) -> BuildRagIndexUseCase:
    return BuildRagIndexUseCase(
        repository,
        embeddings,
        FakeCommunities(),
        "test-embedding",
        stale_after_seconds=7200,
    )


def test_build_is_skipped_when_another_job_holds_the_claim() -> None:
    repository = FakeRepository(claimed=False)
    embeddings = FakeEmbeddings()

    result = asyncio.run(use_case(repository, embeddings).execute("book-1", 3))

    assert result is None
    assert embeddings.called is False
    assert repository.claims == [("book-1", 3, "test-embedding", 7200)]
    assert repository.pending == []
    assert repository.failed == []


def test_daily_quota_marks_pending_and_defers() -> None:
    repository = FakeRepository()
    embeddings = FakeEmbeddings(
        EmbeddingQuotaExhaustedError("daily quota", 21600)
    )

    with pytest.raises(RagBuildDeferred) as raised:
        asyncio.run(use_case(repository, embeddings).execute("book-1", 3))

    assert raised.value.retry_after == 21600
    assert embeddings.called is True
    assert repository.pending == [("book-1", "daily quota")]
    assert repository.failed == []


@pytest.mark.parametrize(
    "error",
    [
        EmbeddingPermanentError("invalid input"),
        EmbeddingConfigurationError("missing key"),
    ],
    ids=["permanent", "configuration"],
)
def test_non_retryable_failures_mark_failed_without_retry(error) -> None:
    repository = FakeRepository()
    embeddings = FakeEmbeddings(error)

    result = asyncio.run(use_case(repository, embeddings).execute("book-1", 3))

    assert result is None
    assert embeddings.called is True
    assert repository.failed == [("book-1", str(error))]
    assert repository.pending == []


def test_transient_failure_is_reraised_for_arq() -> None:
    repository = FakeRepository()
    embeddings = FakeEmbeddings(EmbeddingTransientError("temporary"))

    with pytest.raises(EmbeddingTransientError, match="temporary"):
        asyncio.run(use_case(repository, embeddings).execute("book-1", 3))

    assert embeddings.called is True
    assert repository.failed == [("book-1", "temporary")]
    assert repository.pending == []
