"""RAG index state read against a real PostgreSQL database."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.book import Book
from db.session import session_factory
from rag.adapters.persistence.models import RagIndexStateRecord
from rag.adapters.persistence.repository import PostgresRagRepository
from rag.domain.status import RagIndexStatus
from tests.fixtures.postgres import run_against_postgres

pytestmark = pytest.mark.postgres

MODEL = "test-model"


def add_book(session: AsyncSession, book_id: str) -> None:
    session.add(
        Book(
            id=book_id,
            document_hash=f"hash-{book_id}",
            storage_key=f"books/{book_id}.epub",
            processing_status="ready",
        )
    )


def test_ready_index_state_is_readable(clean_postgres_database) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            add_book(session, "indexed-book")
            session.add(
                RagIndexStateRecord(
                    book_id="indexed-book",
                    status=RagIndexStatus.READY.value,
                    embedding_model=MODEL,
                    graph_revision=3,
                )
            )
            await session.commit()

    asyncio.run(seed())

    async def work(session: AsyncSession) -> None:
        state = await PostgresRagRepository(session).get_index_state("indexed-book")

        assert state is not None
        assert state.status is RagIndexStatus.READY
        assert state.embedding_model == MODEL

    run_against_postgres(work)


def test_failed_index_state_is_visible(clean_postgres_database) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            add_book(session, "failed-book")
            session.add(
                RagIndexStateRecord(
                    book_id="failed-book",
                    status=RagIndexStatus.FAILED.value,
                    embedding_model=MODEL,
                    graph_revision=1,
                    error="quota exhausted",
                )
            )
            await session.commit()

    asyncio.run(seed())

    async def work(session: AsyncSession) -> None:
        state = await PostgresRagRepository(session).get_index_state("failed-book")

        assert state is not None
        assert state.status is RagIndexStatus.FAILED

    run_against_postgres(work)


def test_missing_index_state_is_none(clean_postgres_database) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            add_book(session, "unindexed-book")
            await session.commit()

    asyncio.run(seed())

    async def work(session: AsyncSession) -> None:
        state = await PostgresRagRepository(session).get_index_state("unindexed-book")

        assert state is None

    run_against_postgres(work)
