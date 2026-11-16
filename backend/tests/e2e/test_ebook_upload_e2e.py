import pytest

from tests.fixtures.epub import valid_epub_bytes


@pytest.mark.e2e
def test_upload_is_processed_by_compose_worker(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
    wait_for_ready,
) -> None:
    content = valid_epub_bytes()

    response = e2e_client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", content, "application/epub+zip")},
    )
    assert response.status_code == 202
    upload = response.json()

    status = wait_for_ready(upload["book_id"])
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
