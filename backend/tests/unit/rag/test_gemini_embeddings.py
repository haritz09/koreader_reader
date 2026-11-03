"""Gemini embedding adapter contract."""

import asyncio
import json
import math

import httpx
import pytest

from rag.adapters.embeddings.gemini import GeminiEmbeddingProvider
from rag.domain.errors import (
    EmbeddingConfigurationError,
    EmbeddingQuotaExhaustedError,
    EmbeddingTransientError,
)


def test_batch_request_shape_and_normalization() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("x-goog-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"embeddings": [{"values": [3.0, 0.0, 0.0]}, {"values": [0.0, 0.0, 4.0]}]},
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GeminiEmbeddingProvider(
                api_key="secret",
                model="gemini-embedding-001",
                base_url="https://example.test/v1beta",
                dimensions=3,
                client=client,
            )
            return await provider.embed_documents(["first", "second"])

    vectors = asyncio.run(run())

    assert captured["url"].endswith(
        "/models/gemini-embedding-001:batchEmbedContents"
    )
    assert captured["api_key"] == "secret"
    requests = captured["body"]["requests"]
    assert [request["content"]["parts"][0]["text"] for request in requests] == [
        "first",
        "second",
    ]
    assert {request["taskType"] for request in requests} == {"RETRIEVAL_DOCUMENT"}
    assert {request["outputDimensionality"] for request in requests} == {3}
    assert vectors == [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    assert all(
        math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)
        for vector in vectors
    )


def test_missing_api_key_is_a_configuration_error() -> None:
    provider = GeminiEmbeddingProvider(api_key="", model="gemini-embedding-001")

    with pytest.raises(EmbeddingConfigurationError):
        asyncio.run(provider.embed_documents(["text"]))


def test_server_errors_are_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GeminiEmbeddingProvider(
                api_key="secret",
                model="gemini-embedding-001",
                dimensions=3,
                client=client,
            )
            await provider.embed_documents(["text"])

    with pytest.raises(EmbeddingTransientError):
        asyncio.run(run())


def test_daily_quota_failure_is_not_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [
                                {
                                    "quotaId": (
                                        "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
                                    ),
                                    "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                                }
                            ],
                        }
                    ],
                }
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GeminiEmbeddingProvider(
                api_key="secret",
                model="gemini-embedding-001",
                dimensions=3,
                client=client,
            )
            await provider.embed_documents(["text"])

    with pytest.raises(EmbeddingQuotaExhaustedError):
        asyncio.run(run())


def test_per_minute_rate_limit_stays_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "5"}, text="rate limited")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GeminiEmbeddingProvider(
                api_key="secret",
                model="gemini-embedding-001",
                dimensions=3,
                client=client,
            )
            await provider.embed_documents(["text"])

    with pytest.raises(EmbeddingTransientError) as raised:
        asyncio.run(run())
    assert raised.value.retry_after == 5.0
