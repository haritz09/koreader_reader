"""Spoiler-safe retrieval against a real PostgreSQL database."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects.reading_position import InvalidReadingPositionError
from db.models.book import Book
from db.models.chapter import ChapterRecord
from db.models.chunk import ChunkRecord
from db.session import engine, session_factory
from rag.adapters.persistence.models import RagEmbeddingRecord
from rag.adapters.persistence.retrieval_repository import (
    PostgresRetrievalRepository,
)
from rag.domain.embeddings import EMBEDDING_DIMENSIONS

pytestmark = pytest.mark.postgres

BOOK_ID = "retrieval-book"
CHAPTER_ID = "retrieval-chapter"
MODEL = "test-model"
QUERY = [1.0, *([0.0] * (EMBEDDING_DIMENSIONS - 1))]


def axis(index: int) -> list[float]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    values[index] = 1.0
    return values


def embedding(
    embedding_id: str,
    source_type: str,
    chunk_id: str | None,
    reading_position: float,
    model: str,
    vector: list[float],
) -> RagEmbeddingRecord:
    return RagEmbeddingRecord(
        id=embedding_id,
        book_id=BOOK_ID,
        source_type=source_type,
        source_id=embedding_id,
        chunk_id=chunk_id,
        reading_position=reading_position,
        model=model,
        content_hash=f"hash-{embedding_id}",
        embedding=vector,
    )


def seed_index() -> None:
    async def seed() -> None:
        async with session_factory() as session:
            session.add(
                Book(
                    id=BOOK_ID,
                    document_hash="retrieval-document-hash",
                    storage_key="books/retrieval.epub",
                    processing_status="ready",
                )
            )
            session.add(
                ChapterRecord(
                    id=CHAPTER_ID,
                    book_id=BOOK_ID,
                    title="Chapter",
                    chapter_index=0,
                )
            )
            session.add_all(
                [
                    ChunkRecord(
                        id="chunk-early",
                        book_id=BOOK_ID,
                        chapter_id=CHAPTER_ID,
                        chunk_index=0,
                        text="Jon is betrayed at the wall.",
                        start_pctg=0.1,
                        end_pctg=0.2,
                    ),
                    ChunkRecord(
                        id="chunk-boundary",
                        book_id=BOOK_ID,
                        chapter_id=CHAPTER_ID,
                        chunk_index=1,
                        text="The watch gathers.",
                        start_pctg=0.4,
                        end_pctg=0.5,
                    ),
                    ChunkRecord(
                        id="chunk-late",
                        book_id=BOOK_ID,
                        chapter_id=CHAPTER_ID,
                        chunk_index=2,
                        text="The traitor is revealed.",
                        start_pctg=0.9,
                        end_pctg=1.0,
                    ),
                    ChunkRecord(
                        id="chunk-other-model",
                        book_id=BOOK_ID,
                        chapter_id=CHAPTER_ID,
                        chunk_index=3,
                        text="Old embedding.",
                        start_pctg=0.2,
                        end_pctg=0.3,
                    ),
                ]
            )
            session.add_all(
                [
                    embedding("early-chunk", "chunk", "chunk-early", 0.1, MODEL, axis(1)),
                    embedding("early-entity", "entity", "chunk-early", 0.1, MODEL, axis(0)),
                    embedding(
                        "boundary-chunk", "chunk", "chunk-boundary", 0.5, MODEL, axis(2)
                    ),
                    embedding("late-chunk", "chunk", "chunk-late", 0.9, MODEL, axis(0)),
                    embedding(
                        "orphan-entity", "entity", None, 0.2, MODEL, axis(0)
                    ),
                    embedding(
                        "other-model", "chunk", "chunk-other-model", 0.2, "old-model", axis(0)
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed())


def run_against_postgres(work: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async def main() -> None:
        try:
            async with session_factory() as session:
                await work(session)
        finally:
            await engine.dispose()

    asyncio.run(main())


def test_post_position_chunk_is_excluded_even_when_most_similar() -> None:
    seed_index()

    async def work(session: AsyncSession) -> None:
        chunks = await PostgresRetrievalRepository(session).search_chunks(
            BOOK_ID, 0.5, MODEL, QUERY, 10
        )
        chunk_ids = [result.chunk_id for result in chunks]
        assert "chunk-late" not in chunk_ids
        assert chunk_ids == ["chunk-early", "chunk-boundary"]

    run_against_postgres(work)


def test_boundary_position_is_inclusive() -> None:
    seed_index()

    async def work(session: AsyncSession) -> None:
        chunks = await PostgresRetrievalRepository(session).search_chunks(
            BOOK_ID, 0.5, MODEL, QUERY, 10
        )
        positions = {result.chunk_id: result.reading_position for result in chunks}
        assert positions["chunk-boundary"] == 0.5

    run_against_postgres(work)


def test_multiple_sources_collapse_to_one_chunk_with_the_best_distance() -> None:
    seed_index()

    async def work(session: AsyncSession) -> None:
        chunks = await PostgresRetrievalRepository(session).search_chunks(
            BOOK_ID, 0.5, MODEL, QUERY, 10
        )
        early = [result for result in chunks if result.chunk_id == "chunk-early"]
        assert len(early) == 1
        assert early[0].distance == pytest.approx(0.0)

    run_against_postgres(work)


def test_rows_without_a_chunk_are_skipped() -> None:
    seed_index()

    async def work(session: AsyncSession) -> None:
        chunks = await PostgresRetrievalRepository(session).search_chunks(
            BOOK_ID, 0.5, MODEL, QUERY, 10
        )
        assert all(result.chunk_id for result in chunks)
        assert all(result.chunk_id != "orphan-entity" for result in chunks)

    run_against_postgres(work)


def test_other_embedding_models_are_ignored() -> None:
    seed_index()

    async def work(session: AsyncSession) -> None:
        chunks = await PostgresRetrievalRepository(session).search_chunks(
            BOOK_ID, 0.5, MODEL, QUERY, 10
        )
        assert all(result.chunk_id != "chunk-other-model" for result in chunks)

    run_against_postgres(work)


def test_limit_truncates_the_best_results() -> None:
    seed_index()

    async def work(session: AsyncSession) -> None:
        chunks = await PostgresRetrievalRepository(session).search_chunks(
            BOOK_ID, 0.5, MODEL, QUERY, 1
        )
        assert [result.chunk_id for result in chunks] == ["chunk-early"]

    run_against_postgres(work)


def test_unknown_book_returns_no_chunks() -> None:
    seed_index()

    async def work(session: AsyncSession) -> None:
        chunks = await PostgresRetrievalRepository(session).search_chunks(
            "unknown-book", 0.5, MODEL, QUERY, 10
        )
        assert chunks == []

    run_against_postgres(work)


def test_repository_rejects_an_invalid_position() -> None:
    async def work(session: AsyncSession) -> None:
        with pytest.raises(InvalidReadingPositionError):
            await PostgresRetrievalRepository(session).search_chunks(
                BOOK_ID, 1.5, MODEL, QUERY, 10
            )

    run_against_postgres(work)
