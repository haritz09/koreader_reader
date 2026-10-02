"""Graph and reading-position behaviour against a real PostgreSQL database.

These drive the real repositories and services because the anti-spoiler
guarantee lives in the SQL. A stubbed session would happily pass while the
``reading_position`` predicate was missing from a real query.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.graph import EntityCandidate
from core.domain.value_objects.reading_position import InvalidReadingPositionError
from core.services.entity_resolution import DETERMINISTIC, EntityResolutionService
from core.services.graph_assembly import GraphAssemblyService
from db.models.book import Book
from db.models.chapter import ChapterRecord
from db.models.chunk import ChunkRecord
from db.models.knowledge import EntityRecord, FactRecord
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.repositories.postgres_graph_repository import PostgresGraphRepository
from db.session import engine, session_factory

pytestmark = pytest.mark.postgres

READY = "ready"


class NeverCalledResolver:
    async def resolve_group(
        self, candidates: Sequence[EntityCandidate]
    ) -> list[list[str]]:
        raise AssertionError("the resolver should not be reached for exact name matches")


class AliasResolver:
    async def resolve_group(
        self, candidates: Sequence[EntityCandidate]
    ) -> list[list[str]]:
        return [[candidate.entity_id for candidate in candidates]]


def _run_against_postgres(work: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async def _main() -> None:
        try:
            async with session_factory() as session:
                await work(session)
        finally:
            await engine.dispose()

    asyncio.run(_main())


async def _seed_book(
    session: AsyncSession,
    book_id: str,
    positions: Sequence[float],
    progress: float = 0.0,
    status: str = READY,
) -> dict[int, str]:
    session.add(
        Book(
            id=book_id,
            document_hash=f"{book_id}-document-hash",
            storage_key=f"books/{book_id}.epub",
            processing_status=status,
            progress_position=progress,
        )
    )
    chapter_id = f"{book_id}-chapter-0"
    session.add(
        ChapterRecord(id=chapter_id, book_id=book_id, title="Chapter 1", chapter_index=0)
    )
    chunk_ids: dict[int, str] = {}
    for index, position in enumerate(positions):
        chunk_id = f"{book_id}-chunk-{index}"
        chunk_ids[index] = chunk_id
        session.add(
            ChunkRecord(
                id=chunk_id,
                book_id=book_id,
                chapter_id=chapter_id,
                chunk_index=index,
                text=f"{book_id}-text-{index}",
                start_pctg=position,
                end_pctg=position,
            )
        )
    await session.commit()
    return chunk_ids


async def _add_entities(
    session: AsyncSession,
    book_id: str,
    chunk_ids: dict[int, str],
    rows: Sequence[tuple[int, str, str, str]],
) -> None:
    """Insert mentions as (chunk index, entity id, name, entity type)."""
    for index, entity_id, name, entity_type in rows:
        position = _position_for(book_id, index)
        session.add(
            EntityRecord(
                id=entity_id,
                book_id=book_id,
                chunk_id=chunk_ids[index],
                name=name,
                entity_type=entity_type,
                reading_position=position,
            )
        )
    await session.commit()


async def _add_facts(
    session: AsyncSession,
    book_id: str,
    chunk_ids: dict[int, str],
    rows: Sequence[tuple[int, str, str, str, str]],
) -> None:
    """Insert facts as (chunk index, fact id, subject, object, statement)."""
    for index, fact_id, subject, object_, statement in rows:
        session.add(
            FactRecord(
                id=fact_id,
                book_id=book_id,
                chunk_id=chunk_ids[index],
                statement=statement,
                subject=subject,
                object=object_,
                reading_position=_position_for(book_id, index),
            )
        )
    await session.commit()


_POSITIONS = (0.0, 0.4, 0.9)


def _position_for(book_id: str, index: int) -> float:
    del book_id
    return _POSITIONS[index]


async def _resolve(session: AsyncSession, book_id: str, resolver=None):
    service = EntityResolutionService(
        PostgresKnowledgeRepository(session), resolver or NeverCalledResolver()
    )
    return await service.resolve(book_id)


async def _apply(session: AsyncSession, book_id: str, resolver=None) -> bool:
    resolution = await _resolve(session, book_id, resolver)
    await PostgresKnowledgeRepository(session).apply_resolution(
        book_id, resolution.canonical_by_entity, resolution.method_by_entity
    )
    return resolution.changed


async def _build_graph(session: AsyncSession, book_id: str, position: float):
    return await GraphAssemblyService(PostgresGraphRepository(session)).build(
        book_id, position
    )


def test_resolution_merges_mentions_of_the_same_name_across_chunks(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (2, "book-a-e2", "Alice", "character"),
            ],
        )

        changed = await _apply(session, "book-a")
        graph = await _build_graph(session, "book-a", 1.0)

        assert changed is True
        assert len(graph.nodes) == 1
        assert graph.nodes[0].mention_count == 2

    _run_against_postgres(work)


def test_applying_an_unchanged_resolution_reports_no_change(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (1, "book-a-e2", "Bob", "character"),
            ],
        )

        first = await _apply(session, "book-a")
        second = await _apply(session, "book-a")

        assert first is True
        assert second is False

    _run_against_postgres(work)


def test_resolution_uses_the_resolver_for_near_duplicate_names(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (1, "book-a-e2", "Alicia", "character"),
            ],
        )

        await _apply(session, "book-a", resolver=AliasResolver())
        graph = await _build_graph(session, "book-a", 1.0)

        assert len(graph.nodes) == 1

    _run_against_postgres(work)


def test_graph_hides_entities_beyond_the_requested_position(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (1, "book-a-e2", "Bob", "character"),
                (2, "book-a-e3", "Carol", "character"),
            ],
        )

        graph = await _build_graph(session, "book-a", 0.5)

        assert [node.label for node in graph.nodes] == ["Alice", "Bob"]

    _run_against_postgres(work)


def test_rewinding_after_reading_far_does_not_leak_later_knowledge(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (2, "book-a-e2", "Alicia", "character"),
                (2, "book-a-e3", "Bob", "character"),
            ],
        )
        await _add_facts(
            session,
            "book-a",
            chunk_ids,
            [(2, "book-a-f1", "Alice", "Bob", "Alice is the Ice Queen")],
        )
        resolution = await _resolve(session, "book-a", resolver=AliasResolver())
        await PostgresKnowledgeRepository(session).apply_resolution(
            "book-a", resolution.canonical_by_entity, resolution.method_by_entity
        )

        forward = await _build_graph(session, "book-a", 1.0)
        rewound = await _build_graph(session, "book-a", 0.3)

        assert len(forward.nodes) == 2
        assert len(forward.edges) == 1
        assert [node.label for node in rewound.nodes] == ["Alice"]
        assert rewound.edges == ()

    _run_against_postgres(work)


def test_a_later_alias_cannot_label_a_node_at_an_early_position(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (2, "book-a-e2", "Alicia", "character"),
            ],
        )
        resolution = await _resolve(session, "book-a", resolver=AliasResolver())
        await PostgresKnowledgeRepository(session).apply_resolution(
            "book-a", resolution.canonical_by_entity, resolution.method_by_entity
        )

        early = await _build_graph(session, "book-a", 0.5)
        late = await _build_graph(session, "book-a", 1.0)

        assert early.nodes[0].label == "Alice"
        assert early.nodes[0].first_seen_position == 0.0
        assert early.nodes[0].mention_count == 1
        assert late.nodes[0].label == "Alice"
        assert late.nodes[0].mention_count == 2

    _run_against_postgres(work)


def test_an_edge_needs_both_endpoints_visible(clean_postgres_database: None) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (2, "book-a-e2", "Bob", "character"),
            ],
        )
        await _add_facts(
            session,
            "book-a",
            chunk_ids,
            [(0, "book-a-f1", "Alice", "Bob", "Alice knows Bob")],
        )

        early = await _build_graph(session, "book-a", 0.5)
        late = await _build_graph(session, "book-a", 1.0)

        assert early.edges == ()
        assert len(late.edges) == 1
        assert late.edges[0].source_id == "book-a-e1"
        assert late.edges[0].target_id == "book-a-e2"

    _run_against_postgres(work)


def test_the_graph_never_includes_another_books_knowledge(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        book_a = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            book_a,
            [(0, "book-a-e1", "Alice", "character")],
        )
        book_b = await _seed_book(session, "book-b", _POSITIONS)
        await _add_entities(
            session,
            "book-b",
            book_b,
            [(0, "book-b-e1", "Zebedee", "character")],
        )

        graph = await _build_graph(session, "book-a", 1.0)

        assert [node.label for node in graph.nodes] == ["Alice"]

    _run_against_postgres(work)


def test_the_revision_is_reported_and_increments_atomically(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        await _seed_book(session, "book-a", _POSITIONS)
        repository = PostgresGraphRepository(session)

        assert await repository.get_revision("book-a") == 0

        book_repository = PostgresBookRepository(session)
        assert await book_repository.bump_graph_revision("book-a") == 1
        assert await book_repository.bump_graph_revision("book-a") == 2
        assert await repository.get_revision("book-a") == 2

    _run_against_postgres(work)


def test_the_graph_state_carries_the_stored_progress(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        await _seed_book(session, "book-a", _POSITIONS, progress=0.42, status=READY)

        state = await PostgresBookRepository(session).get_graph_state("book-a")

        assert state is not None
        assert state.progress_position == 0.42
        assert state.processing_status == READY
        assert state.graph_revision == 0
        assert await PostgresBookRepository(session).get_graph_state("missing") is None

    _run_against_postgres(work)


@pytest.mark.parametrize("position", [1.0001, -0.5])
def test_the_graph_read_fails_closed_on_an_out_of_range_position(
    clean_postgres_database: None, position: float
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session, "book-a", chunk_ids, [(0, "book-a-e1", "Alice", "character")]
        )

        with pytest.raises(InvalidReadingPositionError):
            await _build_graph(session, "book-a", position)

    _run_against_postgres(work)


@pytest.mark.parametrize("position", [1.0001, -0.5])
def test_knowledge_retrieval_fails_closed_on_an_out_of_range_position(
    clean_postgres_database: None, position: float
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session, "book-a", chunk_ids, [(0, "book-a-e1", "Alice", "character")]
        )
        repository = PostgresKnowledgeRepository(session)

        for call in (
            repository.get_entities_by_book("book-a", position),
            repository.get_facts_by_book("book-a", position),
            repository.get_events_by_book("book-a", position),
            repository.get_locations_by_book("book-a", position),
        ):
            with pytest.raises(InvalidReadingPositionError):
                await call

    _run_against_postgres(work)


def test_the_database_rejects_an_out_of_range_reading_position(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        session.add(
            EntityRecord(
                id="book-a-bad",
                book_id="book-a",
                chunk_id=chunk_ids[0],
                name="Impossible",
                entity_type="concept",
                reading_position=1.5,
            )
        )

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    _run_against_postgres(work)


def test_the_database_rejects_an_out_of_range_progress_position(
    clean_postgres_database: None,
) -> None:
    async def work(session: AsyncSession) -> None:
        session.add(
            Book(
                id="book-bad",
                document_hash="book-bad-hash",
                storage_key="books/book-bad.epub",
                processing_status=READY,
                progress_position=2.0,
            )
        )

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    _run_against_postgres(work)


def test_resolution_survives_being_applied_twice(clean_postgres_database: None) -> None:
    async def work(session: AsyncSession) -> None:
        chunk_ids = await _seed_book(session, "book-a", _POSITIONS)
        await _add_entities(
            session,
            "book-a",
            chunk_ids,
            [
                (0, "book-a-e1", "Alice", "character"),
                (1, "book-a-e2", "alice", "character"),
            ],
        )
        repository = PostgresKnowledgeRepository(session)

        first = await _resolve(session, "book-a")
        await repository.apply_resolution(
            "book-a", first.canonical_by_entity, first.method_by_entity
        )
        second = await _resolve(session, "book-a")
        await repository.apply_resolution(
            "book-a", second.canonical_by_entity, second.method_by_entity
        )

        stored = await repository.get_resolution("book-a")
        assert stored == {
            "book-a-e1": ("book-a-e1", DETERMINISTIC),
            "book-a-e2": ("book-a-e1", DETERMINISTIC),
        }
        assert second.changed is False

    _run_against_postgres(work)
