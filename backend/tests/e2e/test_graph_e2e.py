"""Graph read against the full Compose stack.

Knowledge is inserted directly so the spoiler assertion is meaningful even
when no LLM key is configured, which is the default in Compose.
"""

import time

import pytest

from tests.fixtures.epub import valid_epub_bytes


def _wait_for_ready(e2e_client, book_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        response = e2e_client.get(f"/api/v1/ebooks/{book_id}")
        assert response.status_code == 200
        status = response.json()
        if status["processing_status"] in {"ready", "failed"}:
            return status
        time.sleep(0.25)
    raise AssertionError(f"book never finished processing: {status}")


def _seed_knowledge(postgres_connection, book_id: str) -> None:
    rows = postgres_connection.execute(
        "SELECT id FROM chunks WHERE book_id = %s ORDER BY chunk_index", (book_id,)
    ).fetchall()
    assert rows, "the worker should have created chunks"
    first_chunk, last_chunk = rows[0][0], rows[-1][0]
    postgres_connection.execute(
        """
        INSERT INTO entities (id, book_id, chunk_id, name, entity_type, reading_position, importance)
        VALUES (%s, %s, %s, 'Alice', 'character', 0.0, 3)
        """,
        (f"{book_id}-e1", book_id, first_chunk),
    )
    postgres_connection.execute(
        """
        INSERT INTO entities (id, book_id, chunk_id, name, entity_type, reading_position, importance)
        VALUES (%s, %s, %s, 'The Ice Queen', 'character', 0.95, 1)
        """,
        (f"{book_id}-e2", book_id, last_chunk),
    )
    postgres_connection.execute(
        """
        INSERT INTO facts (id, book_id, chunk_id, statement, subject, object, reading_position)
        VALUES (%s, %s, %s, 'Alice is the Ice Queen', 'Alice', 'The Ice Queen', 0.95)
        """,
        (f"{book_id}-f1", book_id, last_chunk),
    )
    postgres_connection.commit()


@pytest.mark.e2e
def test_graph_reflects_synced_progress_without_leaking_later_knowledge(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
) -> None:
    content = valid_epub_bytes()
    response = e2e_client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", content, "application/epub+zip")},
    )
    assert response.status_code == 202
    book_id = response.json()["book_id"]
    document_hash = response.json()["document_hash"]

    status = _wait_for_ready(e2e_client, book_id)
    assert status["processing_status"] == "ready", status
    _seed_knowledge(postgres_connection, book_id)

    sync = e2e_client.post(
        "/api/v1/adapters/koreader/sync",
        json={
            "document": document_hash,
            "progress": 0.5,
            "percentage": 50,
            "device": "kobo",
        },
    )
    assert sync.status_code == 202
    assert sync.json()["position"] == 0.5

    graph_response = e2e_client.get(f"/api/v1/ebooks/{book_id}/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()

    assert graph["book_id"] == book_id
    assert graph["position"] == 0.5
    assert [node["label"] for node in graph["nodes"]] == ["Alice"]
    assert graph["edges"] == []


@pytest.mark.e2e
def test_graph_grows_when_the_reader_advances(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
) -> None:
    response = e2e_client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", valid_epub_bytes(), "application/epub+zip")},
    )
    assert response.status_code == 202
    book_id = response.json()["book_id"]
    document_hash = response.json()["document_hash"]

    assert _wait_for_ready(e2e_client, book_id)["processing_status"] == "ready"
    _seed_knowledge(postgres_connection, book_id)

    e2e_client.post(
        "/api/v1/adapters/koreader/sync",
        json={
            "document": document_hash,
            "progress": 1.0,
            "percentage": 100,
            "device": "kobo",
        },
    )
    graph = e2e_client.get(f"/api/v1/ebooks/{book_id}/graph").json()

    assert sorted(node["label"] for node in graph["nodes"]) == ["Alice", "The Ice Queen"]
    assert [edge["statement"] for edge in graph["edges"]] == ["Alice is the Ice Queen"]


@pytest.mark.e2e
def test_rewinding_shrinks_the_graph(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
) -> None:
    response = e2e_client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", valid_epub_bytes(), "application/epub+zip")},
    )
    assert response.status_code == 202
    book_id = response.json()["book_id"]
    document_hash = response.json()["document_hash"]

    assert _wait_for_ready(e2e_client, book_id)["processing_status"] == "ready"
    _seed_knowledge(postgres_connection, book_id)

    def sync_to(position: float) -> dict:
        sync = e2e_client.post(
            "/api/v1/adapters/koreader/sync",
            json={
                "document": document_hash,
                "progress": position,
                "percentage": int(position * 100),
                "device": "kobo",
            },
        )
        assert sync.status_code == 202
        return sync.json()

    forward = sync_to(1.0)
    assert forward["graph_generation_queued"] is True
    assert len(e2e_client.get(f"/api/v1/ebooks/{book_id}/graph").json()["nodes"]) == 2

    rewind = sync_to(0.2)
    assert rewind["graph_generation_queued"] is False
    rewound = e2e_client.get(f"/api/v1/ebooks/{book_id}/graph").json()
    assert [node["label"] for node in rewound["nodes"]] == ["Alice"]
    assert rewound["edges"] == []
