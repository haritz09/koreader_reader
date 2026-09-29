"""Knowledge extraction service."""

import logging
from dataclasses import replace
from uuid import uuid4

from core.domain.entities.chunk import Chunk
from core.domain.entities.knowledge import KnowledgeExtractionResult
from core.ports.knowledge_repository import KnowledgeRepository
from core.ports.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class KnowledgeExtractionService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        knowledge_repository: KnowledgeRepository,
    ) -> None:
        self._llm = llm_provider
        self._repository = knowledge_repository

    async def extract_from_chunks(
        self,
        book_id: str,
        chunks_with_ids: list[tuple[str, Chunk]],
    ) -> None:
        for chunk_id, chunk in chunks_with_ids:
            try:
                result = await self._llm.extract_knowledge(chunk.text)
                tagged = self._tag_result(book_id, chunk_id, chunk.start_pctg, result)
                await self._repository.insert_batch(book_id, tagged)
            except Exception:
                logger.exception(
                    "Knowledge extraction failed for chunk %s, skipping", chunk_id
                )

    @staticmethod
    def _tag_result(
        book_id: str,
        chunk_id: str,
        reading_position: float,
        result: KnowledgeExtractionResult,
    ) -> KnowledgeExtractionResult:
        return KnowledgeExtractionResult(
            entities=[
                replace(
                    e,
                    entity_id=str(uuid4()),
                    book_id=book_id,
                    chunk_id=chunk_id,
                    reading_position=reading_position,
                )
                for e in result.entities
            ],
            facts=[
                replace(
                    f,
                    fact_id=str(uuid4()),
                    book_id=book_id,
                    chunk_id=chunk_id,
                    reading_position=reading_position,
                )
                for f in result.facts
            ],
            events=[
                replace(
                    ev,
                    event_id=str(uuid4()),
                    book_id=book_id,
                    chunk_id=chunk_id,
                    reading_position=reading_position,
                )
                for ev in result.events
            ],
            locations=[
                replace(
                    loc,
                    location_id=str(uuid4()),
                    book_id=book_id,
                    chunk_id=chunk_id,
                    reading_position=reading_position,
                )
                for loc in result.locations
            ],
        )
