from typing import Protocol

from core.domain.entities.knowledge import KnowledgeExtractionResult


class LLMProvider(Protocol):
    """Port for language-model and embedding providers."""

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        """Extract entities, facts, events and locations from a single chunk."""
        ...
