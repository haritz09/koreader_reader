"""Incremental embedding generation."""

import asyncio
import hashlib
import math
from collections.abc import Mapping

from rag.domain.embeddings import EmbeddingSource, EmbeddingSummary
from rag.domain.errors import (
    EmbeddingConfigurationError,
    EmbeddingTransientError,
)
from rag.ports.embedding_provider import EmbeddingProvider
from rag.ports.rag_repository import RagRepository


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _select_pending(
    sources: list[EmbeddingSource],
    existing: Mapping[tuple[str, str], str],
) -> tuple[list[tuple[EmbeddingSource, str]], int, int]:
    pending: list[tuple[EmbeddingSource, str]] = []
    reused = 0
    skipped = 0
    for source in sources:
        digest = content_hash(source.text)
        if existing.get((source.source_type.value, source.source_id)) == digest:
            reused += 1
            continue
        if not source.text.strip():
            skipped += 1
            continue
        pending.append((source, digest))
    return pending, reused, skipped


class EmbedKnowledgeService:
    def __init__(
        self,
        provider: EmbeddingProvider,
        repository: RagRepository,
        *,
        dimensions: int,
        batch_size: int = 20,
        max_attempts: int = 3,
        retry_base_seconds: float = 1.0,
        retry_max_seconds: float = 20.0,
    ) -> None:
        if provider.dimensions != dimensions:
            raise EmbeddingConfigurationError(
                f"Embedding provider returns {provider.dimensions} dimensions, "
                f"expected {dimensions}"
            )
        self._provider = provider
        self._repository = repository
        self._dimensions = dimensions
        self._batch_size = max(1, min(batch_size, provider.max_batch_size))
        self._max_attempts = max(1, max_attempts)
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._retry_max_seconds = max(0.0, retry_max_seconds)

    async def embed_book(self, book_id: str) -> EmbeddingSummary:
        sources = await self._repository.get_embedding_sources(book_id)
        existing = await self._repository.get_existing_hashes(
            book_id, self._provider.model
        )

        pending, reused, skipped = _select_pending(sources, existing)
        vectors = await self._embed_unique(pending)
        await self._repository.upsert_embeddings(
            book_id,
            self._provider.model,
            [(source, digest, vectors[digest]) for source, digest in pending],
        )

        return EmbeddingSummary(
            total=len(sources),
            embedded=len(pending),
            reused=reused,
            skipped=skipped,
        )

    async def _embed_unique(
        self,
        pending: list[tuple[EmbeddingSource, str]],
    ) -> dict[str, list[float]]:
        unique_texts: dict[str, str] = {}
        for source, digest in pending:
            unique_texts.setdefault(digest, source.text)

        digests = list(unique_texts)
        vectors: dict[str, list[float]] = {}
        for start in range(0, len(digests), self._batch_size):
            batch = digests[start : start + self._batch_size]
            batch_vectors = await self._embed_batch([unique_texts[key] for key in batch])
            vectors.update(zip(batch, batch_vectors, strict=True))
        return vectors

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        for attempt in range(1, self._max_attempts + 1):
            try:
                vectors = await self._provider.embed_documents(texts)
                self._validate(vectors, len(texts))
                return vectors
            except EmbeddingTransientError as error:
                if attempt >= self._max_attempts:
                    raise
                delay = min(
                    self._retry_max_seconds,
                    self._retry_base_seconds * 2 ** (attempt - 1),
                )
                if error.retry_after is not None:
                    delay = max(delay, error.retry_after)
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    def _validate(self, vectors: list[list[float]], expected: int) -> None:
        if len(vectors) != expected:
            raise EmbeddingTransientError(
                f"embedding provider returned an incomplete batch of {len(vectors)}"
            )
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise EmbeddingTransientError(
                    "embedding provider returned an invalid vector"
                )
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingTransientError(
                    "embedding provider returned a non-finite vector"
                )
