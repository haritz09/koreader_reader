from typing import Protocol

from core.domain.entities.knowledge import KnowledgeExtractionResult


class LLMError(Exception):
    pass


class LLMConfigurationError(LLMError):
    pass


class LLMPermanentError(LLMError):
    pass


class LLMTransientError(LLMError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMQuotaExhaustedError(LLMError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMProvider(Protocol):
    """Port for language-model and embedding providers."""

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        """Extract entities, facts, events and locations from a single chunk."""
        ...

    async def extract_knowledge_batch(
        self,
        chunks: list[tuple[str, str]],
    ) -> dict[str, KnowledgeExtractionResult]:
        """Extract entities, facts, events and locations from several chunks."""
        ...
