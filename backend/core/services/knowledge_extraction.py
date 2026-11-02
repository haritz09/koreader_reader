"""Knowledge extraction service."""

import asyncio
import logging
import random
from dataclasses import dataclass, replace
from uuid import uuid4

from core.config import settings
from core.domain.entities.chunk import Chunk
from core.domain.entities.knowledge import KnowledgeExtractionResult
from core.domain.errors import KnowledgeExtractionError
from core.ports.knowledge_repository import KnowledgeRepository
from core.ports.llm_provider import (
    LLMConfigurationError,
    LLMPermanentError,
    LLMProvider,
    LLMQuotaExhaustedError,
    LLMTransientError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionSummary:
    total: int
    succeeded: int
    failed: int
    entities: int
    facts: int
    events: int
    locations: int
    error: str | None = None


class _RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self._interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self._interval


class KnowledgeExtractionService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        knowledge_repository: KnowledgeRepository,
        *,
        concurrency: int | None = None,
        max_attempts: int | None = None,
        retry_base_seconds: float | None = None,
        retry_max_seconds: float | None = None,
        requests_per_minute: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._llm = llm_provider
        self._repository = knowledge_repository
        self._concurrency = max(
            1,
            concurrency if concurrency is not None else settings.extraction_concurrency,
        )
        self._batch_size = max(
            1,
            batch_size if batch_size is not None else settings.extraction_batch_size,
        )
        self._max_attempts = max(
            1,
            max_attempts if max_attempts is not None else settings.extraction_max_attempts,
        )
        self._retry_base_seconds = max(
            0.0,
            retry_base_seconds
            if retry_base_seconds is not None
            else settings.extraction_retry_base_seconds,
        )
        self._retry_max_seconds = max(
            0.0,
            retry_max_seconds
            if retry_max_seconds is not None
            else settings.extraction_retry_max_seconds,
        )
        self._limiter = _RateLimiter(
            requests_per_minute
            if requests_per_minute is not None
            else settings.extraction_requests_per_minute
        )

    async def extract_from_chunks(
        self,
        book_id: str,
        chunks_with_ids: list[tuple[str, Chunk]],
    ) -> ExtractionSummary:
        total = len(chunks_with_ids)
        if total == 0:
            return ExtractionSummary(0, 0, 0, 0, 0, 0, 0)

        semaphore = asyncio.Semaphore(self._concurrency)
        batches = [
            chunks_with_ids[index : index + self._batch_size]
            for index in range(0, total, self._batch_size)
        ]
        logger.info(
            "Knowledge extraction started: book=%s chunks=%d batches=%d batch_size=%d "
            "concurrency=%d",
            book_id,
            total,
            len(batches),
            self._batch_size,
            self._concurrency,
        )
        tasks = [
            asyncio.create_task(self._extract_batch(batch, semaphore))
            for batch in batches
        ]

        completed_batches = 0
        succeeded = 0
        failed = 0
        entities = 0
        facts = 0
        events = 0
        locations = 0

        try:
            for completed in asyncio.as_completed(tasks):
                batch, results = await completed
                completed_batches += 1
                expected_ids = {chunk_id for chunk_id, _ in batch}
                if results is None or set(results) != expected_ids:
                    failed += len(batch)
                    if results is not None:
                        logger.warning(
                            "Knowledge extraction returned an incomplete batch of %d chunks",
                            len(batch),
                        )
                    logger.info(
                        "Knowledge extraction progress: book=%s batches=%d/%d chunks=%d/%d "
                        "succeeded=%d failed=%d",
                        book_id,
                        completed_batches,
                        len(batches),
                        succeeded + failed,
                        total,
                        succeeded,
                        failed,
                    )
                    continue

                for chunk_id, chunk in batch:
                    result = results[chunk_id]
                    tagged = self._tag_result(
                        book_id,
                        chunk_id,
                        chunk.start_pctg,
                        result,
                    )
                    await self._repository.insert_batch(book_id, tagged)
                    succeeded += 1
                    entities += len(tagged.entities)
                    facts += len(tagged.facts)
                    events += len(tagged.events)
                    locations += len(tagged.locations)
                logger.info(
                    "Knowledge extraction progress: book=%s batches=%d/%d chunks=%d/%d "
                    "succeeded=%d failed=%d",
                    book_id,
                    completed_batches,
                    len(batches),
                    succeeded + failed,
                    total,
                    succeeded,
                    failed,
                )
        except BaseException as error:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if isinstance(error, LLMQuotaExhaustedError) and succeeded:
                failed = total - succeeded
                logger.warning(
                    "Knowledge extraction stopped at daily quota: book=%s total=%d "
                    "succeeded=%d failed=%d",
                    book_id,
                    total,
                    succeeded,
                    failed,
                )
                return ExtractionSummary(
                    total=total,
                    succeeded=succeeded,
                    failed=failed,
                    entities=entities,
                    facts=facts,
                    events=events,
                    locations=locations,
                    error=(
                        f"{error}; {failed} of {total} chunks were not extracted"
                    ),
                )
            logger.warning(
                "Knowledge extraction aborted: book=%s batches=%d/%d chunks=%d/%d "
                "succeeded=%d failed=%d unprocessed=%d",
                book_id,
                completed_batches,
                len(batches),
                succeeded + failed,
                total,
                succeeded,
                failed,
                total - succeeded - failed,
            )
            raise

        if succeeded == 0:
            logger.error(
                "Knowledge extraction failed: book=%s total=%d failed=%d",
                book_id,
                total,
                failed,
            )
            raise KnowledgeExtractionError(f"All {total} chunks failed extraction")

        summary = ExtractionSummary(
            total=total,
            succeeded=succeeded,
            failed=failed,
            entities=entities,
            facts=facts,
            events=events,
            locations=locations,
            error=f"{failed} of {total} chunks failed extraction" if failed else None,
        )
        if failed:
            logger.warning(
                "Knowledge extraction finished with failures: book=%s total=%d "
                "succeeded=%d failed=%d",
                book_id,
                total,
                succeeded,
                failed,
            )
        logger.info(
            "Knowledge extraction finished: book=%s total=%d succeeded=%d failed=%d "
            "entities=%d facts=%d events=%d locations=%d",
            book_id,
            total,
            succeeded,
            failed,
            entities,
            facts,
            events,
            locations,
        )
        return summary

    async def _extract_batch(
        self,
        batch: list[tuple[str, Chunk]],
        semaphore: asyncio.Semaphore,
    ) -> tuple[
        list[tuple[str, Chunk]],
        dict[str, KnowledgeExtractionResult] | None,
    ]:
        async with semaphore:
            try:
                return batch, await self._extract_batch_with_retry(batch)
            except (LLMConfigurationError, LLMQuotaExhaustedError):
                raise
            except (LLMPermanentError, LLMTransientError) as error:
                logger.warning(
                    "Knowledge extraction failed for a batch of %d chunks: %s",
                    len(batch),
                    error,
                )
                return batch, None
            except Exception:
                logger.exception(
                    "Knowledge extraction failed for a batch of %d chunks",
                    len(batch),
                )
                return batch, None

    async def _extract_batch_with_retry(
        self,
        batch: list[tuple[str, Chunk]],
    ) -> dict[str, KnowledgeExtractionResult]:
        chunks = [(chunk_id, chunk.text) for chunk_id, chunk in batch]
        for attempt in range(1, self._max_attempts + 1):
            await self._limiter.wait()
            try:
                return await self._llm.extract_knowledge_batch(chunks)
            except LLMTransientError as error:
                if attempt >= self._max_attempts:
                    raise
                delay = min(
                    self._retry_max_seconds,
                    self._retry_base_seconds * 2 ** (attempt - 1),
                )
                delay = random.uniform(delay / 2, delay)
                if error.retry_after is not None:
                    delay = max(delay, error.retry_after)
                logger.warning(
                    "LLM request for a batch of %d chunks failed, retrying in %.1fs "
                    "(attempt %d/%d): %s",
                    len(batch),
                    delay,
                    attempt,
                    self._max_attempts,
                    error,
                )
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

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
