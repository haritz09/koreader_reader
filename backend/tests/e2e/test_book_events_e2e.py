"""The processing-status stream end to end against the full Compose stack.

This is the endpoint the library grid subscribes to after an upload, so it has
to report the status the worker actually reached and then close the stream.
"""

import json

import pytest

from tests.fixtures.epub import valid_epub_bytes


def _status_events(response):
    for line in response.iter_lines():
        if line.startswith("data: "):
            yield json.loads(line[len("data: ") :])


@pytest.mark.e2e
def test_the_status_stream_reports_the_status_the_book_reached(
    e2e_enabled,
    clean_postgres_database,
    e2e_client,
) -> None:
    upload = e2e_client.post(
        "/api/v1/ebooks",
        files={"file": ("book.epub", valid_epub_bytes(), "application/epub+zip")},
    )
    assert upload.status_code == 202
    book_id = upload.json()["book_id"]

    with e2e_client.stream("GET", f"/api/v1/ebooks/{book_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [
            event for event in _status_events(response) if event["type"] == "status"
        ]

    reported = e2e_client.get(f"/api/v1/ebooks/{book_id}").json()["processing_status"]
    assert events[-1]["status"] in {"ready", "failed"}
    assert events[-1]["status"] == reported
