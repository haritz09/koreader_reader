"""The processing-status stream the library grid subscribes to.

The stream outlives the request scope, so it opens its own repository through
``LibraryRepositoryFactory``; these tests drive that port with a fake so the
poll loop is exercised without a real database or worker.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from api.dependencies import get_library_repository_factory
from main import app


class StatusBook:
    def __init__(self, status: str | None, error: str | None = None) -> None:
        self.processing_status = status
        self.processing_error = error


class ScriptedLibrary:
    """Reports the scripted statuses in order, then repeats the last one.

    ``None`` stands for a book that is not in the caller's library.
    """

    def __init__(self, statuses: list[str | None]) -> None:
        self._statuses = statuses
        self.reads = 0

    async def get_book(self, owner_id: str, book_id: str) -> StatusBook | None:
        self.reads += 1
        status = self._statuses[min(self.reads - 1, len(self._statuses) - 1)]
        if status is None:
            return None
        return StatusBook(status)


class FailingLibrary:
    """Reaches ``failed`` on the second read, with a reason to report."""

    def __init__(self) -> None:
        self.reads = 0

    async def get_book(self, owner_id: str, book_id: str) -> StatusBook | None:
        self.reads += 1
        if self.reads == 1:
            return StatusBook("processing")
        return StatusBook("failed", error="extraction failed")


def _use(library) -> None:
    @asynccontextmanager
    async def open_library() -> AsyncIterator[object]:
        yield library

    app.dependency_overrides[get_library_repository_factory] = lambda: open_library


def _events(client: TestClient, book_id: str = "book-1") -> list[dict]:
    with client.stream("GET", f"/api/v1/ebooks/{book_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return [
            json.loads(line[len("data: ") :])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]


def test_the_stream_reports_every_status_change_until_the_book_settles(
    monkeypatch,
) -> None:
    monkeypatch.setattr("api.routes.ebooks.STATUS_POLL_SECONDS", 0.01)
    _use(ScriptedLibrary(["pending", "processing", "ready"]))

    try:
        with TestClient(app) as client:
            events = _events(client)
    finally:
        app.dependency_overrides.pop(get_library_repository_factory, None)

    assert [event["type"] for event in events] == ["status", "status", "status"]
    assert [event["status"] for event in events] == ["pending", "processing", "ready"]


def test_the_stream_reports_the_failure_reason_when_processing_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr("api.routes.ebooks.STATUS_POLL_SECONDS", 0.01)
    _use(FailingLibrary())

    try:
        with TestClient(app) as client:
            events = _events(client)
    finally:
        app.dependency_overrides.pop(get_library_repository_factory, None)

    assert events[-1] == {
        "type": "status",
        "status": "failed",
        "error": "extraction failed",
    }


def test_the_stream_reports_an_error_and_closes_when_the_book_is_gone(
    monkeypatch,
) -> None:
    monkeypatch.setattr("api.routes.ebooks.STATUS_POLL_SECONDS", 0.01)
    library = ScriptedLibrary(["processing", None])
    _use(library)

    try:
        with TestClient(app) as client:
            events = _events(client)
    finally:
        app.dependency_overrides.pop(get_library_repository_factory, None)

    assert events == [
        {"type": "status", "status": "processing", "error": None},
        {"type": "error", "message": "Book not found"},
    ]
    assert library.reads == 2
