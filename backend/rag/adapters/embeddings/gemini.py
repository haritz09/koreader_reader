"""Gemini native batch embedding adapter."""

import math
from collections.abc import Sequence

import httpx

from core.config import settings
from lib.http_quota import classify_quota, parse_retry_after
from rag.domain.errors import (
    EmbeddingConfigurationError,
    EmbeddingPermanentError,
    EmbeddingQuotaExhaustedError,
    EmbeddingTransientError,
)

MAX_BATCH_SIZE = 100


class GeminiEmbeddingProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        if api_key is None:
            api_key = settings.embedding_api_key or settings.llm_api_key
        self._api_key = api_key
        self._model = model or settings.embedding_model
        self._base_url = (base_url or settings.embedding_base_url).rstrip("/")
        self._dimensions = dimensions or settings.embedding_dimensions
        self._client = client
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_batch_size(self) -> int:
        return MAX_BATCH_SIZE

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._api_key:
            raise EmbeddingConfigurationError("Embedding API key is not configured")

        payload = {
            "requests": [
                {
                    "model": f"models/{self._model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": "RETRIEVAL_DOCUMENT",
                    "outputDimensionality": self._dimensions,
                }
                for text in texts
            ]
        }
        response = await self._post(
            f"{self._base_url}/models/{self._model}:batchEmbedContents",
            payload,
        )
        return self._parse(response, len(texts))

    async def _post(self, url: str, payload: dict) -> httpx.Response:
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = await self._client.post(
                    url, headers=headers, json=payload, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url, headers=headers, json=payload, timeout=self._timeout
                    )
        except (httpx.TimeoutException, httpx.TransportError) as error:
            raise EmbeddingTransientError(str(error)) from error
        self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        detail = response.text[:300]
        if status in (401, 403, 404, 422):
            raise EmbeddingConfigurationError(
                f"Embedding configuration failed ({status})"
            )
        if status == 429:
            daily, retry_after = classify_quota(response)
            if daily:
                raise EmbeddingQuotaExhaustedError(
                    f"Embedding daily quota exhausted: {detail}",
                    retry_after,
                )
            raise EmbeddingTransientError(
                f"Embedding rate limit hit: {detail}",
                retry_after,
            )
        if status == 408 or status >= 500:
            raise EmbeddingTransientError(
                f"Embedding request failed ({status}): {detail}",
                parse_retry_after(response.headers.get("Retry-After")),
            )
        raise EmbeddingPermanentError(f"Embedding request failed ({status}): {detail}")

    def _parse(self, response: httpx.Response, expected: int) -> list[list[float]]:
        try:
            embeddings = response.json()["embeddings"]
        except (KeyError, TypeError, ValueError) as error:
            raise EmbeddingTransientError(
                "Embedding provider returned an invalid response"
            ) from error
        if not isinstance(embeddings, list) or len(embeddings) != expected:
            raise EmbeddingTransientError(
                f"embedding provider returned an incomplete batch of {len(embeddings)}"
                if isinstance(embeddings, list)
                else "Embedding provider returned an invalid response"
            )

        vectors: list[list[float]] = []
        for item in embeddings:
            values = item.get("values") if isinstance(item, dict) else None
            if not isinstance(values, list) or len(values) != self._dimensions:
                raise EmbeddingTransientError(
                    "embedding provider returned an invalid vector"
                )
            vector = [float(value) for value in values]
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0.0:
                raise EmbeddingTransientError(
                    "embedding provider returned an empty vector"
                )
            vectors.append([value / norm for value in vector])
        return vectors
