"""Deterministic embedding provider fake shared by unit and contract tests."""

from collections.abc import Sequence


class FakeEmbeddingProvider:
    def __init__(
        self,
        vector: Sequence[float] | None = None,
        model: str = "test-model",
        dimensions: int = 3,
    ) -> None:
        self._vector = list(vector) if vector is not None else [0.1, 0.2, 0.3]
        self._model = model
        self._dimensions = dimensions
        self.queries: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_batch_size(self) -> int:
        return 100

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("the read path must not embed documents")

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return list(self._vector)
