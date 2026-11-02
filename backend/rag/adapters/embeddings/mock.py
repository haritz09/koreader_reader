"""Deterministic embedding provider for tests and the e2e stack."""

import hashlib
import math
from collections.abc import Sequence

from core.config import settings


class MockEmbeddingProvider:
    def __init__(self, model: str | None = None, dimensions: int | None = None) -> None:
        self._model = model or settings.embedding_model
        self._dimensions = dimensions or settings.embedding_dimensions

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [
            (digest[index % len(digest)] / 255.0) * 2.0 - 1.0
            for index in range(self._dimensions)
        ]
        norm = math.sqrt(sum(value * value for value in raw)) or 1.0
        return [value / norm for value in raw]
