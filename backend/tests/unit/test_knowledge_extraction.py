"""Tests for knowledge extraction service."""

import asyncio

import pytest

from core.domain.entities.chunk import Chunk
from core.domain.entities.knowledge import (
    Entity,
    Event,
    Fact,
    KnowledgeExtractionResult,
    Location,
)
from core.domain.errors import KnowledgeExtractionError
from core.ports.llm_provider import (
    LLMConfigurationError,
    LLMQuotaExhaustedError,
    LLMTransientError,
)
from core.services.knowledge_extraction import KnowledgeExtractionService


class FakeLLMProvider:
    def __init__(self, result: KnowledgeExtractionResult) -> None:
        self._result = result
        self.batch_sizes: list[int] = []

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        return self._result

    async def extract_knowledge_batch(
        self,
        chunks: list[tuple[str, str]],
    ) -> dict[str, KnowledgeExtractionResult]:
        self.batch_sizes.append(len(chunks))
        return {chunk_id: self._result for chunk_id, _ in chunks}


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.inserted: list[tuple[str, KnowledgeExtractionResult]] = []

    async def insert_batch(
        self,
        book_id: str,
        result: KnowledgeExtractionResult,
    ) -> None:
        self.inserted.append((book_id, result))


def _make_chunk(index: int = 0) -> Chunk:
    return Chunk(
        chapter_id="ch-1",
        chunk_index=index,
        text="Test chunk text",
        start_pctg=0.0,
        end_pctg=0.1,
    )


def _service(
    llm: object,
    repo: FakeKnowledgeRepository,
    **kwargs: object,
) -> KnowledgeExtractionService:
    return KnowledgeExtractionService(
        llm, repo, requests_per_minute=0, **kwargs
    )


def _extraction_result() -> KnowledgeExtractionResult:
    return KnowledgeExtractionResult(
        entities=[
            Entity(entity_id="", book_id="", chunk_id="", name="Frodo", entity_type="character", reading_position=0.0),
        ],
        facts=[
            Fact(fact_id="", book_id="", chunk_id="", statement="Frodo found a ring", subject="Frodo", object="ring", reading_position=0.0),
        ],
        events=[
            Event(event_id="", book_id="", chunk_id="", name="The Fellowship forms", description="The quest began", reading_position=0.0),
        ],
        locations=[
            Location(location_id="", book_id="", chunk_id="", name="Shire", description="Green hills", reading_position=0.0),
        ],
    )


def test_extract_from_chunks_batches_chunks_in_groups_of_three() -> None:
    async def _run() -> None:
        result = _extraction_result()
        llm = FakeLLMProvider(result)
        repo = FakeKnowledgeRepository()
        service = _service(llm, repo)

        chunks = [(f"chunk-{index}", _make_chunk(index)) for index in range(7)]
        await service.extract_from_chunks("book-1", chunks)

        assert len(llm.batch_sizes) == 3
        assert max(llm.batch_sizes) == 3
        assert sum(llm.batch_sizes) == 7
        assert len(repo.inserted) == 7

    asyncio.run(_run())


def test_extract_from_chunks_tags_with_book_id_and_chunk_id() -> None:
    async def _run() -> None:
        result = _extraction_result()
        llm = FakeLLMProvider(result)
        repo = FakeKnowledgeRepository()
        service = _service(llm, repo)

        await service.extract_from_chunks("book-1", [("chunk-42", _make_chunk(0))])

        book_id, stored_result = repo.inserted[0]
        assert book_id == "book-1"
        for e in stored_result.entities:
            assert e.book_id == "book-1"
            assert e.chunk_id == "chunk-42"
        for f in stored_result.facts:
            assert f.book_id == "book-1"
            assert f.chunk_id == "chunk-42"
        for ev in stored_result.events:
            assert ev.book_id == "book-1"
            assert ev.chunk_id == "chunk-42"
        for loc in stored_result.locations:
            assert loc.book_id == "book-1"
            assert loc.chunk_id == "chunk-42"

    asyncio.run(_run())


def test_extract_from_chunks_sets_reading_position_from_chunk() -> None:
    async def _run() -> None:
        result = _extraction_result()
        llm = FakeLLMProvider(result)
        repo = FakeKnowledgeRepository()
        service = _service(llm, repo)

        chunk_with_pctg = Chunk(
            chapter_id="ch-1",
            chunk_index=0,
            text="text",
            start_pctg=0.35,
            end_pctg=0.45,
        )
        await service.extract_from_chunks("book-1", [("c1", chunk_with_pctg)])

        _, stored_result = repo.inserted[0]
        for item in [*stored_result.entities, *stored_result.facts, *stored_result.events, *stored_result.locations]:
            assert item.reading_position == 0.35

    asyncio.run(_run())


def test_extract_from_chunks_fails_when_all_chunks_fail() -> None:
    async def _run() -> None:
        class FailingLLM:
            async def extract_knowledge_batch(
                self,
                chunks: list[tuple[str, str]],
            ) -> dict[str, KnowledgeExtractionResult]:
                raise RuntimeError("API down")

        repo = FakeKnowledgeRepository()
        service = _service(FailingLLM(), repo, max_attempts=1)

        chunks = [("c1", _make_chunk(0)), ("c2", _make_chunk(1))]
        with pytest.raises(KnowledgeExtractionError):
            await service.extract_from_chunks("book-1", chunks)

        assert len(repo.inserted) == 0

    asyncio.run(_run())


def test_extract_from_chunks_retries_transient_failures() -> None:
    async def _run() -> None:
        class FlakyLLM:
            def __init__(self) -> None:
                self.call_count = 0

            async def extract_knowledge_batch(
                self,
                chunks: list[tuple[str, str]],
            ) -> dict[str, KnowledgeExtractionResult]:
                self.call_count += 1
                if self.call_count < 3:
                    raise LLMTransientError("rate limited")
                return {
                    chunk_id: _extraction_result() for chunk_id, _ in chunks
                }

        llm = FlakyLLM()
        repo = FakeKnowledgeRepository()
        service = _service(
            llm,
            repo,
            max_attempts=3,
            retry_base_seconds=0,
            retry_max_seconds=0,
        )

        summary = await service.extract_from_chunks("book-1", [("c1", _make_chunk())])

        assert llm.call_count == 3
        assert summary.succeeded == 1
        assert summary.failed == 0
        assert len(repo.inserted) == 1

    asyncio.run(_run())


def test_extract_from_chunks_does_not_retry_configuration_errors() -> None:
    async def _run() -> None:
        class MisconfiguredLLM:
            def __init__(self) -> None:
                self.call_count = 0

            async def extract_knowledge_batch(
                self,
                chunks: list[tuple[str, str]],
            ) -> dict[str, KnowledgeExtractionResult]:
                self.call_count += 1
                raise LLMConfigurationError("invalid key")

        llm = MisconfiguredLLM()
        repo = FakeKnowledgeRepository()
        service = _service(llm, repo, max_attempts=3)

        with pytest.raises(LLMConfigurationError):
            await service.extract_from_chunks("book-1", [("c1", _make_chunk())])

        assert llm.call_count == 1

    asyncio.run(_run())


def test_extract_from_chunks_returns_partial_when_quota_runs_out_after_success() -> None:
    async def _run() -> None:
        class QuotaLLM:
            def __init__(self) -> None:
                self.call_count = 0

            async def extract_knowledge_batch(
                self,
                chunks: list[tuple[str, str]],
            ) -> dict[str, KnowledgeExtractionResult]:
                self.call_count += 1
                if self.call_count == 2:
                    raise LLMQuotaExhaustedError("daily quota exhausted", 3600)
                return {
                    chunk_id: _extraction_result() for chunk_id, _ in chunks
                }

        llm = QuotaLLM()
        repo = FakeKnowledgeRepository()
        service = _service(llm, repo, concurrency=1, batch_size=3)
        chunks = [(f"c{index}", _make_chunk(index)) for index in range(4)]

        summary = await service.extract_from_chunks("book-1", chunks)

        assert llm.call_count == 2
        assert len(repo.inserted) == 3
        assert summary.total == 4
        assert summary.succeeded == 3
        assert summary.failed == 1
        assert "daily quota exhausted" in summary.error

    asyncio.run(_run())


def test_extract_from_chunks_limits_concurrency() -> None:
    async def _run() -> None:
        class TrackingLLM:
            def __init__(self) -> None:
                self.active = 0
                self.max_active = 0

            async def extract_knowledge_batch(
                self,
                chunks: list[tuple[str, str]],
            ) -> dict[str, KnowledgeExtractionResult]:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                await asyncio.sleep(0.01)
                self.active -= 1
                return {
                    chunk_id: _extraction_result() for chunk_id, _ in chunks
                }

        llm = TrackingLLM()
        repo = FakeKnowledgeRepository()
        service = _service(llm, repo, concurrency=2)
        chunks = [(f"c{index}", _make_chunk(index)) for index in range(7)]

        summary = await service.extract_from_chunks("book-1", chunks)

        assert summary.succeeded == 7
        assert llm.max_active <= 2

    asyncio.run(_run())


def test_extract_from_chunks_assigns_unique_ids() -> None:
    async def _run() -> None:
        result = _extraction_result()
        llm = FakeLLMProvider(result)
        repo = FakeKnowledgeRepository()
        service = _service(llm, repo)

        await service.extract_from_chunks("book-1", [("c1", _make_chunk(0))])

        _, stored_result = repo.inserted[0]
        ids = [e.entity_id for e in stored_result.entities]
        assert len(ids) == len(set(ids))

    asyncio.run(_run())
