"""Removing a book end to end against the full Compose stack."""

import time

import pytest

from tests.fixtures.epub import valid_epub_bytes


def _upload(client, content: bytes):
    return client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", content, "application/epub+zip")},
    )


def _wait_for_ready(client, book_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/ebooks/{book_id}")
        assert response.status_code == 200
        status = response.json()
        if status["processing_status"] in {"ready", "failed"}:
            return status
        time.sleep(0.25)
    raise AssertionError(f"book never finished processing: {status}")


@pytest.mark.e2e
def test_deleting_a_book_hides_it_and_reuploading_restores_the_same_book(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
) -> None:
    content = valid_epub_bytes()
    upload = _upload(e2e_client, content)
    assert upload.status_code == 202
    book_id = upload.json()["book_id"]
    assert _wait_for_ready(e2e_client, book_id)["processing_status"] == "ready"

    deleted = e2e_client.delete(f"/api/v1/ebooks/{book_id}")
    assert deleted.status_code == 204
    assert e2e_client.get("/api/v1/ebooks").json()["books"] == []
    assert e2e_client.get(f"/api/v1/ebooks/{book_id}").status_code == 404

    # The content is kept, so the same identity comes back without reprocessing.
    restored = _upload(e2e_client, content)
    assert restored.status_code == 202
    assert restored.json()["book_id"] == book_id
    assert [book["book_id"] for book in e2e_client.get("/api/v1/ebooks").json()["books"]] == [
        book_id
    ]

    book_rows = postgres_connection.execute(
        "SELECT COUNT(*) FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    assert book_rows == (1,)


@pytest.mark.e2e
def test_deleting_a_book_in_another_library_is_not_found(
    e2e_enabled,
    clean_postgres_database,
    e2e_client,
) -> None:
    upload = _upload(e2e_client, valid_epub_bytes(identifier="owned-by-first"))
    assert upload.status_code == 202
    book_id = upload.json()["book_id"]

    # A second anonymous owner gets its own cookie and library.
    second_session = e2e_client.post("/api/v1/session")
    assert second_session.status_code == 201
    assert e2e_client.get("/api/v1/ebooks").json()["books"] == []
    assert e2e_client.get(f"/api/v1/ebooks/{book_id}").status_code == 404
    assert e2e_client.delete(f"/api/v1/ebooks/{book_id}").status_code == 404
