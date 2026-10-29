import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from adapters.llm.openai_provider import OpenAIProvider
from core.domain.entities.graph import EntityCandidate
from core.domain.entities.knowledge import KnowledgeExtractionResult
from core.ports.llm_provider import LLMQuotaExhaustedError

logger = logging.getLogger(__name__)


class FailoverLLMProvider:
    def __init__(self, providers: list[OpenAIProvider]) -> None:
        if not providers:
            raise ValueError("At least one LLM provider is required")
        self._providers = providers
        self._exhausted_until: dict[str, float] = {}

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        return await self._call("extract_knowledge", chunk_text)

    async def extract_knowledge_batch(
        self,
        chunks: list[tuple[str, str]],
    ) -> dict[str, KnowledgeExtractionResult]:
        return await self._call("extract_knowledge_batch", chunks)

    async def resolve_group(
        self,
        candidates: list[EntityCandidate],
    ) -> list[list[str]]:
        return await self._call("resolve_group", candidates)

    async def _call(self, method: str, *args: object) -> object:
        now = time.monotonic()
        available = [
            provider
            for provider in self._providers
            if self._exhausted_until.get(provider.model, 0.0) <= now
        ]
        if not available:
            raise LLMQuotaExhaustedError(
                self._exhausted_message(),
                self._retry_after(now),
            )

        last_error: LLMQuotaExhaustedError | None = None
        for provider in available:
            try:
                return await getattr(provider, method)(*args)
            except LLMQuotaExhaustedError as error:
                wait = error.retry_after
                if wait is None:
                    wait = _seconds_until_midnight_pacific()
                self._exhausted_until[provider.model] = time.monotonic() + max(1.0, wait)
                last_error = error
                logger.warning(
                    "Model %s exhausted its daily quota; trying the next model",
                    provider.model,
                )

        raise LLMQuotaExhaustedError(
            self._exhausted_message(),
            self._retry_after(time.monotonic()),
        ) from last_error

    def _retry_after(self, now: float) -> float | None:
        waits = [until - now for until in self._exhausted_until.values()]
        return max(0.0, min(waits)) if waits else None

    def _exhausted_message(self) -> str:
        models = ", ".join(provider.model for provider in self._providers)
        return f"All configured models exhausted their daily quota: {models}"


def _seconds_until_midnight_pacific() -> float:
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return max(1.0, tomorrow.timestamp() - time.time())
