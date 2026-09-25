from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    get_book_repository,
    get_ebook_processing_queue,
    get_ebook_storage,
)
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory
from main import app
from tests.fixtures.epub import valid_epub_bytes


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


async def real_book_repository() -> AsyncIterator[PostgresBookRepository]:
    async with session_factory() as session:
        yield PostgresBookRepository(session)


@pytest.mark.postgres
def test_upload_persists_book_and_deduplicates_against_postgres(
    clean_postgres_database,
    postgres_connection,
) -> None:
    storage = RecordingStorage()
    queue = RecordingQueue()
    app.dependency_overrides[get_book_repository] = real_book_repository
    app.dependency_overrides[get_ebook_storage] = lambda: storage
    app.dependency_overrides[get_ebook_processing_queue] = lambda: queue
    client = TestClient(app)
    content = valid_epub_bytes()

    try:
        first_response = client.post(
            "/api/v1/ebooks",
            files={"file": ("book.epub", content, "application/epub+zip")},
        )
        duplicate_response = client.post(
            "/api/v1/ebooks",
            files={"file": ("book-copy.epub", content, "application/epub+zip")},
        )
        status_response = client.get(
            f"/api/v1/ebooks/{first_response.json()['book_id']}"
        )
    finally:
        app.dependency_overrides.clear()

    assert first_response.status_code == 202
    assert duplicate_response.status_code == 202
    assert duplicate_response.json() == first_response.json()
    assert status_response.status_code == 200
    assert status_response.json()["processing_status"] == "pending"
    assert len(storage.saved) == 1
    assert len(queue.enqueued) == 1

    row = postgres_connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT document_hash) FROM books"
    ).fetchone()
    assert row == (1, 1)
