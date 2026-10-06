import asyncio
from collections.abc import Awaitable, Callable, Sequence

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.chunk import Chunk
from core.domain.entities.knowledge import (
    Entity,
    Event,
    Fact,
    KnowledgeExtractionResult,
    Location,
)
from core.services.knowledge_extraction import KnowledgeExtractionService
from db.models.book import Book
from db.models.chapter import ChapterRecord
from db.models.chunk import ChunkRecord
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.session import engine, session_factory

pytestmark = pytest.mark.postgres


class _ChunkTaggingLLMProvider:
    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        return KnowledgeExtractionResult(
            entities=[
                Entity(
                    entity_id="",
                    book_id="",
                    chunk_id="",
                    name=f"entity-{chunk_text}",
                    entity_type="concept",
                    reading_position=0.0,
                )
            ],
            facts=[
                Fact(
                    fact_id="",
                    book_id="",
                    chunk_id="",
                    statement=f"fact-{chunk_text}",
                    subject=None,
                    object=None,
                    reading_position=0.0,
                )
            ],
            events=[
                Event(
                    event_id="",
                    book_id="",
                    chunk_id="",
                    name=f"event-{chunk_text}",
                    description=f"event-{chunk_text}",
                    reading_position=0.0,
                )
            ],
            locations=[
                Location(
                    location_id="",
                    book_id="",
                    chunk_id="",
                    name=f"location-{chunk_text}",
                    description=None,
                    reading_position=0.0,
                )
            ],
        )


def _chunk_id(book_id: str, index: int) -> str:
    return f"{book_id}-chunk-{index}"


def _run_against_postgres(
    work: Callable[[AsyncSession], Awaitable[None]],
) -> None:
    async def _main() -> None:
        try:
            async with session_factory() as session:
                await work(session)
        finally:
            await engine.dispose()

    asyncio.run(_main())


async def _seed_chunks(
    session: AsyncSession,
    book_id: str,
    positions: Sequence[float],
) -> list[Chunk]:
    chapter_id = f"{book_id}-chapter-0"
    session.add(
        Book(
            id=book_id,
            document_hash=f"{book_id}-document-hash",
            storage_key=f"books/{book_id}.epub",
        )
    )
    session.add(
        ChapterRecord(
            id=chapter_id,
            book_id=book_id,
            title="Chapter 1",
            chapter_index=0,
        )
    )
    chunks = [
        Chunk(
            chapter_id=chapter_id,
            chunk_index=index,
            text=f"{book_id}-text-{index}",
            start_pctg=position,
            end_pctg=position,
        )
        for index, position in enumerate(positions)
    ]
    session.add_all(
        ChunkRecord(
            id=_chunk_id(book_id, index),
            book_id=book_id,
            chapter_id=chapter_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            start_pctg=chunk.start_pctg,
            end_pctg=chunk.end_pctg,
        )
        for index, chunk in enumerate(chunks)
    )
    await session.commit()
    return chunks


async def _extract_knowledge(
    session: AsyncSession,
    book_id: str,
    chunks: Sequence[Chunk],
) -> None:
    service = KnowledgeExtractionService(
        _ChunkTaggingLLMProvider(),
        PostgresKnowledgeRepository(session),
    )
    await service.extract_from_chunks(
        book_id,
        [(_chunk_id(book_id, index), chunk) for index, chunk in enumerate(chunks)],
    )


async def _visible_chunk_ids(
    repository: PostgresKnowledgeRepository,
    book_id: str,
    reading_position: float,
) -> dict[str, list[str]]:
    entities = await repository.get_entities_by_book(book_id, reading_position)
    facts = await repository.get_facts_by_book(book_id, reading_position)
    events = await repository.get_events_by_book(book_id, reading_position)
    locations = await repository.get_locations_by_book(book_id, reading_position)
    return {
        "entities": [entity.chunk_id for entity in entities],
        "facts": [fact.chunk_id for fact in facts],
        "events": [event.chunk_id for event in events],
        "locations": [location.chunk_id for location in locations],
    }


def test_retrieval_hides_knowledge_from_chunks_beyond_current_position(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunks = await _seed_chunks(session, "book-a", [0.0, 0.4, 0.9])
        await _extract_knowledge(session, "book-a", chunks)

        repository = PostgresKnowledgeRepository(session)
        visible = await _visible_chunk_ids(repository, "book-a", 0.5)

        assert visible == {
            "entities": ["book-a-chunk-0", "book-a-chunk-1"],
            "facts": ["book-a-chunk-0", "book-a-chunk-1"],
            "events": ["book-a-chunk-0", "book-a-chunk-1"],
            "locations": ["book-a-chunk-0", "book-a-chunk-1"],
        }

    _run_against_postgres(work)


def test_retrieval_includes_knowledge_at_exactly_the_current_position(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunks = await _seed_chunks(session, "book-a", [0.0, 0.4, 0.9])
        await _extract_knowledge(session, "book-a", chunks)

        repository = PostgresKnowledgeRepository(session)
        visible = await _visible_chunk_ids(repository, "book-a", 0.4)

        assert visible["entities"] == ["book-a-chunk-0", "book-a-chunk-1"]
        assert visible["facts"] == ["book-a-chunk-0", "book-a-chunk-1"]
        assert visible["events"] == ["book-a-chunk-0", "book-a-chunk-1"]
        assert visible["locations"] == ["book-a-chunk-0", "book-a-chunk-1"]

    _run_against_postgres(work)


def test_retrieval_at_start_of_book_returns_only_the_first_chunk(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunks = await _seed_chunks(session, "book-a", [0.0, 0.4, 0.9])
        await _extract_knowledge(session, "book-a", chunks)

        repository = PostgresKnowledgeRepository(session)
        visible = await _visible_chunk_ids(repository, "book-a", 0.0)

        assert visible == {
            "entities": ["book-a-chunk-0"],
            "facts": ["book-a-chunk-0"],
            "events": ["book-a-chunk-0"],
            "locations": ["book-a-chunk-0"],
        }

    _run_against_postgres(work)


def test_retrieval_at_end_of_book_returns_every_chunk(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunks = await _seed_chunks(session, "book-a", [0.0, 0.4, 0.9])
        await _extract_knowledge(session, "book-a", chunks)

        repository = PostgresKnowledgeRepository(session)
        visible = await _visible_chunk_ids(repository, "book-a", 1.0)

        assert visible == {
            "entities": ["book-a-chunk-0", "book-a-chunk-1", "book-a-chunk-2"],
            "facts": ["book-a-chunk-0", "book-a-chunk-1", "book-a-chunk-2"],
            "events": ["book-a-chunk-0", "book-a-chunk-1", "book-a-chunk-2"],
            "locations": ["book-a-chunk-0", "book-a-chunk-1", "book-a-chunk-2"],
        }

    _run_against_postgres(work)


def test_retrieval_returns_nothing_when_no_chunk_has_been_read(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunks = await _seed_chunks(session, "book-a", [0.5, 0.9])
        await _extract_knowledge(session, "book-a", chunks)

        repository = PostgresKnowledgeRepository(session)
        visible = await _visible_chunk_ids(repository, "book-a", 0.1)

        assert visible == {
            "entities": [],
            "facts": [],
            "events": [],
            "locations": [],
        }

    _run_against_postgres(work)


def test_retrieval_never_returns_knowledge_from_another_book(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        book_a_chunks = await _seed_chunks(session, "book-a", [0.0])
        await _extract_knowledge(session, "book-a", book_a_chunks)
        book_b_chunks = await _seed_chunks(session, "book-b", [0.0])
        await _extract_knowledge(session, "book-b", book_b_chunks)

        repository = PostgresKnowledgeRepository(session)
        visible = await _visible_chunk_ids(repository, "book-a", 1.0)

        assert visible == {
            "entities": ["book-a-chunk-0"],
            "facts": ["book-a-chunk-0"],
            "events": ["book-a-chunk-0"],
            "locations": ["book-a-chunk-0"],
        }

    _run_against_postgres(work)
