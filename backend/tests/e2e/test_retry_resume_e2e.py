import pytest

from tests.fixtures.epub import valid_epub_bytes


@pytest.mark.e2e
def test_retry_resumes_only_the_chunks_left_unprocessed(
    e2e_enabled,
    clean_postgres_database,
    postgres_connection,
    e2e_client,
    wait_for_ready,
) -> None:
    response = e2e_client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", valid_epub_bytes(), "application/epub+zip")},
    )
    assert response.status_code == 202
    book_id = response.json()["book_id"]
    assert wait_for_ready(book_id)["processing_status"] == "ready"

    postgres_connection.execute(
        "UPDATE chunks SET extracted_at = now() - interval '1 hour' "
        "WHERE book_id = %s AND chunk_index = 0",
        (book_id,),
    )
    postgres_connection.execute(
        "UPDATE chunks SET extracted_at = NULL WHERE book_id = %s AND chunk_index = 1",
        (book_id,),
    )
    postgres_connection.execute(
        "UPDATE books SET processing_status = 'partial' WHERE id = %s",
        (book_id,),
    )
    postgres_connection.commit()

    retry = e2e_client.post(f"/api/v1/ebooks/{book_id}/retry")
    assert retry.status_code == 202
    final = wait_for_ready(book_id)
    assert final["processing_status"] == "ready"
    assert final["chunks_total"] == final["chunks_extracted"]

    rows = postgres_connection.execute(
        "SELECT chunk_index, extracted_at FROM chunks WHERE book_id = %s ORDER BY chunk_index",
        (book_id,),
    ).fetchall()
    assert [row[1] is not None for row in rows] == [True, True]
    assert rows[0][1] < rows[1][1]
