"""Library membership behaviour against a real PostgreSQL database.

Covers the ownership boundary and the soft-delete/restore round trip, which the
in-memory contract tests cannot prove.
"""

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_owner, get_ebook_processing_queue, get_ebook_storage
from db.repositories.postgres_library_repository import PostgresLibraryRepository
from db.session import engine, session_factory
from main import app
from tests.conftest import TEST_OWNER_ID
from tests.fixtures.epub import valid_epub_bytes

pytestmark = pytest.mark.postgres


class RecordingStorage:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bytes]] = []

    async def save(self, storage_key: str, content: bytes) -> str:
        self.saved.append((storage_key, content))
        return storage_key

    async def delete(self, storage_key: str) -> None:
        return None


class RecordingQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str]] = []

    async def enqueue(self, book_id: str, storage_key: str) -> None:
        self.enqueued.append((book_id, storage_key))


def _upload(client, content: bytes):
    return client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", content, "application/epub+zip")},
    )


def test_soft_deleting_a_book_hides_it_and_reuploading_restores_the_same_book(
    clean_postgres_database,
    postgres_connection,
    postgres_app_client,
) -> None:
    app.dependency_overrides[get_ebook_storage] = lambda: RecordingStorage()
    app.dependency_overrides[get_ebook_processing_queue] = lambda: RecordingQueue()
    content = valid_epub_bytes()

    try:
        upload = _upload(postgres_app_client, content)
        assert upload.status_code == 202
        book_id = upload.json()["book_id"]

        deleted = postgres_app_client.delete(f"/api/v1/ebooks/{book_id}")
        listed = postgres_app_client.get("/api/v1/ebooks")
        status_response = postgres_app_client.get(f"/api/v1/ebooks/{book_id}")

        restored = _upload(postgres_app_client, content)
        listed_again = postgres_app_client.get("/api/v1/ebooks")
    finally:
        app.dependency_overrides.clear()

    assert deleted.status_code == 204
    assert listed.json() == {"books": []}
    assert status_response.status_code == 404

    assert restored.status_code == 202
    assert restored.json()["book_id"] == book_id
    assert [book["book_id"] for book in listed_again.json()["books"]] == [book_id]

    # The content is kept, never purged, and the membership is live again.
    book_rows = postgres_connection.execute(
        "SELECT COUNT(*) FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    live_memberships = postgres_connection.execute(
        "SELECT COUNT(*) FROM user_books "
        "WHERE book_id = %s AND owner_id = %s AND deleted_at IS NULL",
        (book_id, TEST_OWNER_ID),
    ).fetchone()
    assert book_rows == (1,)
    assert live_memberships == (1,)


def test_an_owner_cannot_read_or_delete_another_owners_book(
    clean_postgres_database,
    postgres_connection,
    postgres_app_client,
) -> None:
    app.dependency_overrides[get_ebook_storage] = lambda: RecordingStorage()
    app.dependency_overrides[get_ebook_processing_queue] = lambda: RecordingQueue()
    postgres_connection.execute(
        "INSERT INTO users (id, is_anonymous, created_at) "
        "VALUES ('owner-2', true, now()) ON CONFLICT (id) DO NOTHING"
    )
    postgres_connection.commit()

    try:
        upload = _upload(postgres_app_client, valid_epub_bytes())
        book_id = upload.json()["book_id"]

        app.dependency_overrides[get_current_owner] = lambda: "owner-2"
        other_list = postgres_app_client.get("/api/v1/ebooks")
        other_status = postgres_app_client.get(f"/api/v1/ebooks/{book_id}")
        other_graph = postgres_app_client.get(f"/api/v1/ebooks/{book_id}/graph")
        other_delete = postgres_app_client.delete(f"/api/v1/ebooks/{book_id}")

        app.dependency_overrides[get_current_owner] = lambda: TEST_OWNER_ID
        owner_list = postgres_app_client.get("/api/v1/ebooks")
    finally:
        app.dependency_overrides.clear()

    assert other_list.json() == {"books": []}
    assert other_status.status_code == 404
    assert other_graph.status_code == 404
    assert other_delete.status_code == 404
    assert [book["book_id"] for book in owner_list.json()["books"]] == [book_id]


def test_a_shared_book_keeps_one_content_row_for_two_owners(
    clean_postgres_database,
    postgres_connection,
    postgres_app_client,
) -> None:
    app.dependency_overrides[get_ebook_storage] = lambda: RecordingStorage()
    app.dependency_overrides[get_ebook_processing_queue] = lambda: RecordingQueue()
    postgres_connection.execute(
        "INSERT INTO users (id, is_anonymous, created_at) "
        "VALUES ('owner-2', true, now()) ON CONFLICT (id) DO NOTHING"
    )
    postgres_connection.commit()
    content = valid_epub_bytes()

    try:
        first = _upload(postgres_app_client, content)
        app.dependency_overrides[get_current_owner] = lambda: "owner-2"
        second = _upload(postgres_app_client, content)
        second_list = postgres_app_client.get("/api/v1/ebooks")
    finally:
        app.dependency_overrides.clear()

    assert first.json()["book_id"] == second.json()["book_id"]
    assert [book["book_id"] for book in second_list.json()["books"]] == [
        second.json()["book_id"]
    ]

    content_rows = postgres_connection.execute(
        "SELECT COUNT(*) FROM books WHERE document_hash = %s",
        (first.json()["document_hash"],),
    ).fetchone()
    membership_rows = postgres_connection.execute(
        "SELECT COUNT(*) FROM user_books WHERE book_id = %s",
        (first.json()["book_id"],),
    ).fetchone()
    assert content_rows == (1,)
    assert membership_rows == (2,)


def _run_against_postgres(work: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async def _main() -> None:
        session: AsyncSession | None = None
        try:
            async with session_factory() as active_session:
                session = active_session
                await work(active_session)
        finally:
            if session is not None:
                await session.close()
            await engine.dispose()

    asyncio.run(_main())


def test_a_long_lived_reader_sees_status_changes_made_elsewhere(
    clean_postgres_database,
    postgres_connection,
) -> None:
    """The processing-status stream polls for minutes on a single session.

    SQLAlchemy's identity map hands back the entity it loaded first without
    refreshing it, so a cached read would freeze the stream on the status seen
    at the start and the browser would never leave "processing".
    """
    postgres_connection.execute(
        "INSERT INTO books "
        "(id, document_hash, storage_key, processing_status, progress_position) "
        "VALUES ('book-1', 'hash-1', 'books/1.epub', 'processing', 0.0)"
    )
    postgres_connection.execute(
        "INSERT INTO user_books (owner_id, book_id, added_at) VALUES (%s, 'book-1', now())",
        (TEST_OWNER_ID,),
    )
    postgres_connection.commit()

    seen: list[str | None] = []

    async def work(session: AsyncSession) -> None:
        library = PostgresLibraryRepository(session)

        first = await library.get_book(TEST_OWNER_ID, "book-1")
        seen.append(first.processing_status if first is not None else None)

        postgres_connection.execute(
            "UPDATE books SET processing_status = 'ready' WHERE id = 'book-1'"
        )
        postgres_connection.commit()

        second = await library.get_book(TEST_OWNER_ID, "book-1")
        seen.append(second.processing_status if second is not None else None)

    _run_against_postgres(work)

    assert seen == ["processing", "ready"]
