"""Incremental embedding generation."""

import asyncio
import hashlib
import math

from rag.domain.embeddings import EmbeddingSource, EmbeddingSummary
from rag.domain.errors import (
    EmbeddingConfigurationError,
    EmbeddingTransientError,
)
from rag.ports.embedding_provider import EmbeddingProvider
from rag.ports.rag_repository import RagRepository


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        self._batch_size = max(1, batch_size)
        self._max_attempts = max(1, max_attempts)
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._retry_max_seconds = max(0.0, retry_max_seconds)

    async def embed_book(self, book_id: str) -> EmbeddingSummary:
        sources = await self._repository.get_embedding_sources(book_id)
        existing = await self._repository.get_existing_hashes(
            book_id, self._provider.model
        )

        pending: list[tuple[EmbeddingSource, str]] = []
        reused = 0
        for source in sources:
            digest = content_hash(source.text)
            if existing.get((source.source_type.value, source.source_id)) == digest:
                reused += 1
                continue
            pending.append((source, digest))

        embedded = 0
        for start in range(0, len(pending), self._batch_size):
            batch = pending[start : start + self._batch_size]
            vectors = await self._embed_batch([source.text for source, _ in batch])
            await self._repository.upsert_embeddings(
                book_id,
                self._provider.model,
                self._dimensions,
                [
                    (source, digest, vector)
                    for (source, digest), vector in zip(batch, vectors, strict=True)
                ],
            )
            embedded += len(batch)

        return EmbeddingSummary(total=len(sources), embedded=embedded, reused=reused)

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
