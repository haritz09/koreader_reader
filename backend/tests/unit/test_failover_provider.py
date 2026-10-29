import asyncio

import pytest

from adapters.llm.failover_provider import FailoverLLMProvider
from core.domain.entities.knowledge import KnowledgeExtractionResult
from core.ports.llm_provider import LLMQuotaExhaustedError, LLMTransientError


class FakeModelProvider:
    def __init__(
        self,
        model: str,
        failures: list[Exception] | None = None,
    ) -> None:
        self.model = model
        self.calls = 0
        self._failures = list(failures or [])

    async def extract_knowledge_batch(
        self,
        chunks: list[tuple[str, str]],
    ) -> dict[str, KnowledgeExtractionResult]:
        self.calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return {
            chunk_id: KnowledgeExtractionResult(
                entities=[],
                facts=[],
                events=[],
                locations=[],
            )
            for chunk_id, _ in chunks
        }


def test_daily_quota_switches_to_the_fallback_model_and_stays_there() -> None:
    async def _run() -> None:
        primary = FakeModelProvider(
            "primary",
            [LLMQuotaExhaustedError("daily quota", 3600)],
        )
        fallback = FakeModelProvider("fallback")
        provider = FailoverLLMProvider([primary, fallback])

        await provider.extract_knowledge_batch([("c1", "text")])
        await provider.extract_knowledge_batch([("c2", "text")])

        assert primary.calls == 1
        assert fallback.calls == 2

    asyncio.run(_run())


def test_a_rate_limit_does_not_switch_models() -> None:
    async def _run() -> None:
        primary = FakeModelProvider(
            "primary",
            [LLMTransientError("rate limited", 30)],
        )
        fallback = FakeModelProvider("fallback")
        provider = FailoverLLMProvider([primary, fallback])

        with pytest.raises(LLMTransientError):
            await provider.extract_knowledge_batch([("c1", "text")])

        assert primary.calls == 1
        assert fallback.calls == 0

    asyncio.run(_run())


def test_all_exhausted_models_raise_a_clear_error_and_stop_calling_them() -> None:
    async def _run() -> None:
        primary = FakeModelProvider(
            "primary",
            [LLMQuotaExhaustedError("daily quota", 3600)],
        )
        fallback = FakeModelProvider(
            "fallback",
            [LLMQuotaExhaustedError("daily quota", 7200)],
        )
        provider = FailoverLLMProvider([primary, fallback])

        with pytest.raises(LLMQuotaExhaustedError) as error:
            await provider.extract_knowledge_batch([("c1", "text")])

        assert "All configured models exhausted" in str(error.value)
        assert primary.calls == 1
        assert fallback.calls == 1

        with pytest.raises(LLMQuotaExhaustedError):
            await provider.extract_knowledge_batch([("c2", "text")])

        assert primary.calls == 1
        assert fallback.calls == 1

    asyncio.run(_run())


def test_a_quota_error_without_a_retry_after_uses_a_positive_wait() -> None:
    async def _run() -> None:
        primary = FakeModelProvider(
            "primary",
            [LLMQuotaExhaustedError("daily quota")],
        )
        provider = FailoverLLMProvider([primary])

        with pytest.raises(LLMQuotaExhaustedError) as error:
            await provider.extract_knowledge_batch([("c1", "text")])

        assert error.value.retry_after is not None
        assert error.value.retry_after > 0

    asyncio.run(_run())
