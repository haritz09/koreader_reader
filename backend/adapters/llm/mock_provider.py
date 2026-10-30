from collections.abc import Sequence

from core.domain.entities.graph import EntityCandidate
from core.domain.entities.knowledge import KnowledgeExtractionResult


class MockLLMProvider:
    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        return _empty_result()

    async def extract_knowledge_batch(
        self,
        chunks: list[tuple[str, str]],
    ) -> dict[str, KnowledgeExtractionResult]:
        return {chunk_id: _empty_result() for chunk_id, _ in chunks}

    async def resolve_group(
        self,
        candidates: Sequence[EntityCandidate],
    ) -> list[list[str]]:
        return []


def _empty_result() -> KnowledgeExtractionResult:
    return KnowledgeExtractionResult(
        entities=[],
        facts=[],
        events=[],
        locations=[],
    )
