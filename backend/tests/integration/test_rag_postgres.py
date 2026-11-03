"""RAG persistence against a real PostgreSQL database."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.book import Book
from db.models.chapter import ChapterRecord
from db.models.chunk import ChunkRecord
from db.models.knowledge import EntityRecord, EventRecord, FactRecord, LocationRecord
from db.session import engine, session_factory
from rag.adapters.persistence.models import (
    RagCommunityMemberRecord,
    RagCommunityRecord,
    RagCommunityRunRecord,
    RagEmbeddingRecord,
    RagIndexStateRecord,
)
from rag.adapters.persistence.repository import PostgresRagRepository
from rag.clustering.graph import build_cluster_graph
from rag.clustering.leiden import LeidenCommunityDetector
from rag.domain.clustering import ClusterParameters
from rag.domain.embeddings import EmbeddingSource, EmbeddingSourceType
from rag.domain.status import RagIndexStatus

pytestmark = pytest.mark.postgres

BOOK_ID = "rag-book"
PARAMETERS = ClusterParameters(
    resolution=1.0,
    max_levels=1,
    min_size=2,
    seed=42,
    objective="modularity",
    fact_edge_weight=2.0,
    cooccurrence_edge_weight=1.0,
)


def run_against_postgres(work: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async def main() -> None:
        try:
            async with session_factory() as session:
                await work(session)
        finally:
            await engine.dispose()

    asyncio.run(main())


def seed_book() -> None:
    async def seed() -> None:
        async with session_factory() as session:
            session.add(
                Book(
                    id=BOOK_ID,
                    document_hash="rag-document-hash",
                    storage_key="books/rag.epub",
                    processing_status="ready",
                )
            )
            session.add(
                ChapterRecord(
                    id="rag-chapter",
                    book_id=BOOK_ID,
                    title="Chapter",
                    chapter_index=0,
                )
            )
            session.add_all(
                [
                    ChunkRecord(
                        id="rag-chunk-1",
                        book_id=BOOK_ID,
                        chapter_id="rag-chapter",
                        chunk_index=0,
                        text="Alice meets Bob in Paris.",
                        start_pctg=0.1,
                        end_pctg=0.3,
                    ),
                    ChunkRecord(
                        id="rag-chunk-2",
                        book_id=BOOK_ID,
                        chapter_id="rag-chapter",
                        chunk_index=1,
                        text="Al remembers the duel.",
                        start_pctg=0.4,
                        end_pctg=0.6,
                    ),
                ]
            )
            session.add_all(
                [
                    EntityRecord(
                        id="rag-e1",
                        book_id=BOOK_ID,
                        chunk_id="rag-chunk-1",
                        name="Alice",
                        entity_type="character",
                        description="The protagonist",
                        aliases=["Al"],
                        reading_position=0.1,
                        canonical_id="rag-e1",
                    ),
                    EntityRecord(
                        id="rag-e2",
                        book_id=BOOK_ID,
                        chunk_id="rag-chunk-2",
                        name="Al",
                        entity_type="character",
                        aliases=[],
                        reading_position=0.4,
                        canonical_id="rag-e1",
                    ),
                    EntityRecord(
                        id="rag-e3",
                        book_id=BOOK_ID,
                        chunk_id="rag-chunk-1",
                        name="Bob",
                        entity_type="character",
                        aliases=[],
                        reading_position=0.1,
                        canonical_id="rag-e3",
                    ),
                    EventRecord(
                        id="rag-ev1",
                        book_id=BOOK_ID,
                        chunk_id="rag-chunk-2",
                        name="The Duel",
                        description="A decisive fight",
                        reading_position=0.4,
                    ),
                    LocationRecord(
                        id="rag-l1",
                        book_id=BOOK_ID,
                        chunk_id="rag-chunk-1",
                        name="Paris",
                        description="A city",
                        reading_position=0.1,
                    ),
                ]
            )
            session.add_all(
                [
                    FactRecord(
                        id="rag-f1",
                        book_id=BOOK_ID,
                        chunk_id="rag-chunk-1",
                        statement="Alice meets Bob",
                        subject="Alice",
                        object="Bob",
                        reading_position=0.1,
                    ),
                    FactRecord(
                        id="rag-f2",
                        book_id=BOOK_ID,
                        chunk_id="rag-chunk-2",
                        statement="Al remembers the duel",
                        subject="Al",
                        object="The Duel",
                        reading_position=0.4,
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed())


def vector(value: float = 1.0) -> list[float]:
    return [value] + [0.0] * 767


def test_embedding_sources_keep_each_source_position() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)

        sources = await repository.get_embedding_sources(BOOK_ID)

        by_type = {
            source_type: [source for source in sources if source.source_type == source_type]
            for source_type in EmbeddingSourceType
        }
        assert len(by_type[EmbeddingSourceType.CHUNK]) == 2
        assert len(by_type[EmbeddingSourceType.ENTITY]) == 3
        assert len(by_type[EmbeddingSourceType.FACT]) == 2
        assert len(by_type[EmbeddingSourceType.EVENT]) == 1
        assert len(by_type[EmbeddingSourceType.LOCATION]) == 1
        assert {
            source.reading_position
            for source in by_type[EmbeddingSourceType.ENTITY]
        } == {0.1, 0.4}
        assert all(source.chunk_id for source in sources)

    run_against_postgres(work)


def test_embedding_upsert_is_idempotent() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)
        sources = await repository.get_embedding_sources(BOOK_ID)
        chunk = next(
            source
            for source in sources
            if source.source_type == EmbeddingSourceType.CHUNK
        )

        await repository.upsert_embeddings(
            BOOK_ID,
            "gemini-embedding-001",
            [(chunk, "first-hash", vector())],
        )
        await repository.upsert_embeddings(
            BOOK_ID,
            "gemini-embedding-001",
            [(chunk, "second-hash", vector(0.5))],
        )

        hashes = await repository.get_existing_hashes(
            BOOK_ID, "gemini-embedding-001"
        )
        count = await session.scalar(
            select(func.count()).select_from(RagEmbeddingRecord)
        )
        assert hashes[(chunk.source_type.value, chunk.source_id)] == "second-hash"
        assert count == 1

    run_against_postgres(work)


def test_community_run_is_stored_and_swapped_atomically() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)
        sources = await repository.get_cluster_sources(BOOK_ID)
        assert len(sources.entity_mentions) == 3
        assert len(sources.named_mentions) == 2

        graph = build_cluster_graph(BOOK_ID, sources, PARAMETERS)
        tree = LeidenCommunityDetector().detect(graph, PARAMETERS)

        first_run = await repository.save_community_run(
            BOOK_ID,
            graph_revision=0,
            embedding_model="gemini-embedding-001",
            graph=graph,
            tree=tree,
            status=RagIndexStatus.READY,
        )
        assert await repository.needs_build(
            BOOK_ID, 0, "gemini-embedding-001", 3600
        ) is False

        second_run = await repository.save_community_run(
            BOOK_ID,
            graph_revision=0,
            embedding_model="gemini-embedding-001",
            graph=graph,
            tree=tree,
            status=RagIndexStatus.READY,
        )
        state = await session.get(RagIndexStateRecord, BOOK_ID)
        runs = await session.scalar(
            select(func.count()).select_from(RagCommunityRunRecord)
        )
        communities = await session.scalar(
            select(func.count()).select_from(RagCommunityRecord)
        )
        assert first_run != second_run
        assert state is not None
        assert state.current_run_id == second_run
        assert state.rag_revision == 2
        assert runs == 1
        assert communities == len(tree.communities)

    run_against_postgres(work)


def test_delete_by_book_clears_the_index() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)
        sources = await repository.get_cluster_sources(BOOK_ID)
        tree = LeidenCommunityDetector().detect(
            build_cluster_graph(BOOK_ID, sources, PARAMETERS), PARAMETERS
        )
        await repository.save_community_run(
            BOOK_ID,
            graph_revision=1,
            embedding_model="gemini-embedding-001",
            graph=build_cluster_graph(BOOK_ID, sources, PARAMETERS),
            tree=tree,
            status=RagIndexStatus.READY,
        )
        embeddings = await repository.get_embedding_sources(BOOK_ID)
        chunk = embeddings[0]
        await repository.upsert_embeddings(
            BOOK_ID, "gemini-embedding-001", [(chunk, "hash", vector())]
        )

        await repository.delete_by_book(BOOK_ID)

        for model in (
            RagEmbeddingRecord,
            RagCommunityRunRecord,
            RagCommunityRecord,
            RagIndexStateRecord,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0

    run_against_postgres(work)


def test_claim_build_is_exclusive_and_reclaims_a_stale_building_state() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)

        assert await repository.claim_build(BOOK_ID, 2, "model", 3600) is True
        assert await repository.claim_build(BOOK_ID, 2, "model", 3600) is False

        await session.execute(
            update(RagIndexStateRecord)
            .where(RagIndexStateRecord.book_id == BOOK_ID)
            .values(updated_at=datetime.now(UTC) - timedelta(seconds=7200))
        )
        await session.commit()

        assert await repository.claim_build(BOOK_ID, 2, "model", 3600) is True

    run_against_postgres(work)


def test_pending_build_is_retried_even_without_a_revision_change() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)

        assert await repository.claim_build(BOOK_ID, 2, "model", 3600) is True
        await repository.mark_pending(BOOK_ID, "daily quota")

        assert await repository.needs_build(BOOK_ID, 2, "model", 3600) is True

    run_against_postgres(work)


def test_community_members_store_their_first_seen_position() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)
        sources = await repository.get_cluster_sources(BOOK_ID)
        graph = build_cluster_graph(BOOK_ID, sources, PARAMETERS)
        tree = LeidenCommunityDetector().detect(graph, PARAMETERS)
        await repository.save_community_run(
            BOOK_ID,
            graph_revision=0,
            embedding_model="gemini-embedding-001",
            graph=graph,
            tree=tree,
            status=RagIndexStatus.READY,
        )

        positions = {node.node_id: node.reading_position for node in graph.nodes}
        rows = (await session.execute(select(RagCommunityMemberRecord))).scalars().all()

        assert rows
        for row in rows:
            assert row.first_seen_position == pytest.approx(positions[row.node_id])

    run_against_postgres(work)


def test_embedding_uniqueness_is_scoped_to_a_book() -> None:
    async def work(session: AsyncSession) -> None:
        repository = PostgresRagRepository(session)
        session.add(
            Book(
                id="rag-book-2",
                document_hash="rag-document-hash-2",
                storage_key="books/rag-2.epub",
                processing_status="ready",
            )
        )
        await session.commit()

        shared = EmbeddingSource(
            source_type=EmbeddingSourceType.ENTITY,
            source_id="shared-entity",
            chunk_id=None,
            reading_position=0.1,
            text="Shared entity",
        )

        await repository.upsert_embeddings(
            BOOK_ID, "gemini-embedding-001", [(shared, "hash-1", vector())]
        )
        await repository.upsert_embeddings(
            "rag-book-2", "gemini-embedding-001", [(shared, "hash-2", vector())]
        )

        count = await session.scalar(
            select(func.count())
            .select_from(RagEmbeddingRecord)
            .where(RagEmbeddingRecord.source_id == "shared-entity")
        )
        assert count == 2

    run_against_postgres(work)


@pytest.fixture(autouse=True)
def seeded(clean_postgres_database) -> None:
    seed_book()
