"""Chat against the full Compose stack, with the mock LLM and embeddings."""

import time

import pytest

from tests.fixtures.epub import valid_epub_bytes


def _wait_for_chat(e2e_client, book_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = e2e_client.post(
            f"/api/v1/ebooks/{book_id}/chat",
            json={"question": "What happens in this book?"},
        )
        if last.status_code == 200:
            return last.json()
        assert last.status_code == 409, last.text
        time.sleep(0.25)
    raise AssertionError(f"chat never became available: {last.text}")


def _chunk_positions(postgres_connection, book_id: str) -> dict[str, float]:
    rows = postgres_connection.execute(
        """
        SELECT DISTINCT chunk_id, reading_position
        FROM rag_embeddings
        WHERE book_id = %s AND chunk_id IS NOT NULL
        """,
        (book_id,),
    ).fetchall()
    return {chunk_id: position for chunk_id, position in rows}


def _upload_and_wait(e2e_client, wait_for_ready) -> tuple[str, str]:
    response = e2e_client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", valid_epub_bytes(), "application/epub+zip")},
    )
    assert response.status_code == 202
    book_id = response.json()["book_id"]
    assert wait_for_ready(book_id)["processing_status"] == "ready"
    return book_id, response.json()["document_hash"]


@pytest.mark.e2e
def test_chat_returns_only_evidence_visible_at_the_stored_position(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
    wait_for_ready,
) -> None:
    book_id = _upload_and_wait(e2e_client, wait_for_ready)[0]
    positions = _chunk_positions(postgres_connection, book_id)
    assert positions, "the worker should have embedded chunks"

    body = _wait_for_chat(e2e_client, book_id)

    assert body["book_id"] == book_id
    assert body["position"] == 0.0
    assert isinstance(body["answer"], str) and body["answer"]
    assert body["sources"], "the opening chunk should be visible at position zero"
    for source in body["sources"]:
        assert source["reading_position"] <= body["position"]
        assert positions[source["chunk_id"]] == source["reading_position"]


@pytest.mark.e2e
def test_chat_sources_grow_with_reading_progress(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
    wait_for_ready,
) -> None:
    book_id, document_hash = _upload_and_wait(e2e_client, wait_for_ready)
    positions = _chunk_positions(postgres_connection, book_id)
    assert len(positions) > 1, "the fixture should produce more than one chunk"

    opening = _wait_for_chat(e2e_client, book_id)
    opening_ids = {source["chunk_id"] for source in opening["sources"]}

    sync = e2e_client.post(
        "/api/v1/adapters/koreader/sync",
        json={
            "document": document_hash,
            "progress": 1.0,
            "percentage": 100,
            "device": "kobo",
        },
    )
    assert sync.status_code == 202

    finished = e2e_client.post(
        f"/api/v1/ebooks/{book_id}/chat",
        json={"question": "What happens in this book?"},
    )
    assert finished.status_code == 200
    body = finished.json()
    finished_ids = {source["chunk_id"] for source in body["sources"]}

    assert body["position"] == 1.0
    assert opening_ids <= finished_ids
    assert len(finished_ids) > len(opening_ids)
    assert finished_ids <= set(positions)
    assert all(
        source["reading_position"] <= 1.0 for source in body["sources"]
    )
