import os
import time

import httpx
import pytest

from tests.fixtures.epub import valid_epub_bytes


@pytest.mark.e2e
def test_upload_is_processed_by_compose_worker(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
) -> None:
    base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
    content = valid_epub_bytes()

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        response = client.post(
            "/api/v1/ebooks",
            files={"file": ("book.epub", content, "application/epub+zip")},
        )
        assert response.status_code == 202
        upload = response.json()

        deadline = time.monotonic() + 30
        status = None
        while time.monotonic() < deadline:
            status_response = client.get(f"/api/v1/ebooks/{upload['book_id']}")
            assert status_response.status_code == 200
            status = status_response.json()
            if status["processing_status"] in {"ready", "failed"}:
                break
            time.sleep(0.25)

    assert status is not None
    assert status["processing_status"] == "ready", status

    row = postgres_connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM books WHERE id = %s),
            (SELECT COUNT(*) FROM chapters WHERE book_id = %s),
            (SELECT COUNT(*) FROM chunks WHERE book_id = %s)
        """,
        (upload["book_id"], upload["book_id"], upload["book_id"]),
    ).fetchone()
    assert row == (1, 2, 2)
