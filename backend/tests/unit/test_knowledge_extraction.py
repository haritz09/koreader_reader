"""Tests for knowledge extraction service."""

import asyncio

from core.domain.entities.chunk import Chunk
from core.domain.entities.knowledge import (
    Entity,
    Event,
    Fact,
    KnowledgeExtractionResult,
    Location,
)
from core.services.knowledge_extraction import KnowledgeExtractionService


class FakeLLMProvider:
    def __init__(self, result: KnowledgeExtractionResult) -> None:
        self._result = result
        self.call_count = 0

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        self.call_count += 1
        return self._result


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


def _extraction_result() -> KnowledgeExtractionResult:
    return KnowledgeExtractionResult(
        entities=[
            Entity(entity_id="", book_id="", chunk_id="", name="Frodo", entity_type="character", reading_position=0.0),
        ],
        facts=[
            Fact(fact_id="", book_id="", chunk_id="", statement="Frodo found a ring", subject="Frodo", object="ring", reading_position=0.0),
        ],
        events=[
            Event(event_id="", book_id="", chunk_id="", description="The quest began", reading_position=0.0),
        ],
        locations=[
            Location(location_id="", book_id="", chunk_id="", name="Shire", description="Green hills", reading_position=0.0),
        ],
    )


def test_extract_from_chunks_calls_llm_for_each_chunk() -> None:
    async def _run() -> None:
        result = _extraction_result()
        llm = FakeLLMProvider(result)
        repo = FakeKnowledgeRepository()
        service = KnowledgeExtractionService(llm, repo)

        chunks = [("chunk-1", _make_chunk(0)), ("chunk-2", _make_chunk(1))]
        await service.extract_from_chunks("book-1", chunks)

        assert llm.call_count == 2
        assert len(repo.inserted) == 2

    asyncio.run(_run())


def test_extract_from_chunks_tags_with_book_id_and_chunk_id() -> None:
    async def _run() -> None:
        result = _extraction_result()
        llm = FakeLLMProvider(result)
        repo = FakeKnowledgeRepository()
        service = KnowledgeExtractionService(llm, repo)

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
        service = KnowledgeExtractionService(llm, repo)

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


def test_extract_from_chunks_continues_on_llm_failure() -> None:
    async def _run() -> None:
        class FailingLLM:
            async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
                raise RuntimeError("API down")

        repo = FakeKnowledgeRepository()
        service = KnowledgeExtractionService(FailingLLM(), repo)

        chunks = [("c1", _make_chunk(0)), ("c2", _make_chunk(1))]
        await service.extract_from_chunks("book-1", chunks)

        assert len(repo.inserted) == 0

    asyncio.run(_run())


def test_extract_from_chunks_assigns_unique_ids() -> None:
    async def _run() -> None:
        result = _extraction_result()
        llm = FakeLLMProvider(result)
        repo = FakeKnowledgeRepository()
        service = KnowledgeExtractionService(llm, repo)

        await service.extract_from_chunks("book-1", [("c1", _make_chunk(0))])

        _, stored_result = repo.inserted[0]
        ids = [e.entity_id for e in stored_result.entities]
        assert len(ids) == len(set(ids))

    asyncio.run(_run())
