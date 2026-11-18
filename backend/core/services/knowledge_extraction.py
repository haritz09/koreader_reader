"""Knowledge extraction service."""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
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

ExtractionProgressReporter = Callable[[int], Awaitable[None]]

_ChunkBatch = list[tuple[str, Chunk]]
_BatchResults = dict[str, KnowledgeExtractionResult] | None


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


@dataclass
class _Progress:
    succeeded: int = 0
    failed: int = 0
    entities: int = 0
    facts: int = 0
    events: int = 0
    locations: int = 0

    @property
    def processed(self) -> int:
        return self.succeeded + self.failed

    def fail_batch(self, size: int) -> None:
        self.failed += size

    def fail_remaining(self, total: int) -> None:
        self.failed = total - self.succeeded

    def record(self, result: KnowledgeExtractionResult) -> None:
        self.succeeded += 1
        self.entities += len(result.entities)
        self.facts += len(result.facts)
        self.events += len(result.events)
        self.locations += len(result.locations)


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


def _split_batches(chunks: _ChunkBatch, batch_size: int) -> list[_ChunkBatch]:
    return [chunks[index : index + batch_size] for index in range(0, len(chunks), batch_size)]


def _received_every_chunk(batch: _ChunkBatch, results: _BatchResults) -> bool:
    return results is not None and set(results) == {chunk_id for chunk_id, _ in batch}


async def _completed_batches(
    tasks: list[asyncio.Task],
) -> AsyncIterator[tuple[_ChunkBatch, _BatchResults]]:
    for completed in asyncio.as_completed(tasks):
        yield await completed


async def _cancel(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _report_progress(
    reporter: ExtractionProgressReporter | None,
    extracted: int,
) -> None:
    if reporter is not None:
        await reporter(extracted)


def _log_progress(
    book_id: str,
    completed_batches: int,
    total_batches: int,
    progress: _Progress,
    total: int,
) -> None:
    logger.info(
        "Knowledge extraction progress: book=%s batches=%d/%d chunks=%d/%d "
        "succeeded=%d failed=%d",
        book_id,
        completed_batches,
        total_batches,
        progress.processed,
        total,
        progress.succeeded,
        progress.failed,
    )


def _finished_summary(
    book_id: str,
    total: int,
    progress: _Progress,
    error: str | None = None,
) -> ExtractionSummary:
    if progress.succeeded == 0:
        logger.error(
            "Knowledge extraction failed: book=%s total=%d failed=%d",
            book_id,
            total,
            progress.failed,
        )
        raise KnowledgeExtractionError(f"All {total} chunks failed extraction")
    failure = error
    if failure is None and progress.failed:
        failure = f"{progress.failed} of {total} chunks failed extraction"
    return ExtractionSummary(
        total=total,
        succeeded=progress.succeeded,
        failed=progress.failed,
        entities=progress.entities,
        facts=progress.facts,
        events=progress.events,
        locations=progress.locations,
        error=failure,
    )


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
        chunks_with_ids: _ChunkBatch,
        on_progress: ExtractionProgressReporter | None = None,
    ) -> ExtractionSummary:
        total = len(chunks_with_ids)
        if total == 0:
            return ExtractionSummary(0, 0, 0, 0, 0, 0, 0)

        batches = _split_batches(chunks_with_ids, self._batch_size)
        logger.info(
            "Knowledge extraction started: book=%s chunks=%d batches=%d batch_size=%d "
            "concurrency=%d",
            book_id,
            total,
            len(batches),
            self._batch_size,
            self._concurrency,
        )

        semaphore = asyncio.Semaphore(self._concurrency)
        tasks = [
            asyncio.create_task(self._extract_batch(batch, semaphore)) for batch in batches
        ]
        progress = _Progress()
        completed_batches = 0

        try:
            async for batch, results in _completed_batches(tasks):
                completed_batches += 1
                await self._consume_batch(book_id, batch, results, progress)
                _log_progress(book_id, completed_batches, len(batches), progress, total)
                await _report_progress(on_progress, progress.succeeded)
        except BaseException as error:
            await _cancel(tasks)
            if isinstance(error, LLMQuotaExhaustedError) and progress.succeeded:
                progress.fail_remaining(total)
                logger.warning(
                    "Knowledge extraction stopped at daily quota: book=%s total=%d "
                    "succeeded=%d failed=%d",
                    book_id,
                    total,
                    progress.succeeded,
                    progress.failed,
                )
                return _finished_summary(
                    book_id,
                    total,
                    progress,
                    error=f"{error}; {progress.failed} of {total} chunks were not extracted",
                )
            _log_abort(book_id, completed_batches, len(batches), progress, total)
            raise

        summary = _finished_summary(book_id, total, progress)
        _log_finished(book_id, summary)
        return summary

    async def _consume_batch(
        self,
        book_id: str,
        batch: _ChunkBatch,
        results: _BatchResults,
        progress: _Progress,
    ) -> None:
        if not _received_every_chunk(batch, results):
            progress.fail_batch(len(batch))
            if results is not None:
                logger.warning(
                    "Knowledge extraction returned an incomplete batch of %d chunks",
                    len(batch),
                )
            return

        for chunk_id, chunk in batch:
            tagged = self._tag_result(
                book_id,
                chunk_id,
                chunk.start_pctg,
                results[chunk_id],
            )
            await self._repository.insert_batch(book_id, chunk_id, tagged)
            progress.record(tagged)

    async def _extract_batch(
        self,
        batch: _ChunkBatch,
        semaphore: asyncio.Semaphore,
    ) -> tuple[_ChunkBatch, _BatchResults]:
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
        batch: _ChunkBatch,
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


def _log_abort(
    book_id: str,
    completed_batches: int,
    total_batches: int,
    progress: _Progress,
    total: int,
) -> None:
    logger.warning(
        "Knowledge extraction aborted: book=%s batches=%d/%d chunks=%d/%d "
        "succeeded=%d failed=%d unprocessed=%d",
        book_id,
        completed_batches,
        total_batches,
        progress.processed,
        total,
        progress.succeeded,
        progress.failed,
        total - progress.processed,
    )


def _log_finished(book_id: str, summary: ExtractionSummary) -> None:
    if summary.failed:
        logger.warning(
            "Knowledge extraction finished with failures: book=%s total=%d "
            "succeeded=%d failed=%d",
            book_id,
            summary.total,
            summary.succeeded,
            summary.failed,
        )
    logger.info(
        "Knowledge extraction finished: book=%s total=%d succeeded=%d failed=%d "
        "entities=%d facts=%d events=%d locations=%d",
        book_id,
        summary.total,
        summary.succeeded,
        summary.failed,
        summary.entities,
        summary.facts,
        summary.events,
        summary.locations,
    )
