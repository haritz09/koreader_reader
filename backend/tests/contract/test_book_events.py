"""The processing-status stream the library grid subscribes to."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from api.dependencies import (
    get_book_status_subscriber,
    get_library_repository_factory,
)
from core.ports.book_status_events import BookStatusEvent
from main import app


class StatusBook:
    def __init__(self, status: str | None, error: str | None = None) -> None:
        self.processing_status = status
        self.processing_error = error


class ScriptedLibrary:
    """Reports the scripted statuses in order, then repeats the last one."""

    def __init__(self, statuses: list[str | None]) -> None:
        self._statuses = statuses
        self.reads = 0

    async def get_book(self, owner_id: str, book_id: str) -> StatusBook | None:
        self.reads += 1
        status = self._statuses[min(self.reads - 1, len(self._statuses) - 1)]
        if status is None:
            return None
        return StatusBook(status)


class ScriptedSubscription:
    def __init__(self, events: list[BookStatusEvent]) -> None:
        self._events = list(events)
        self.closed = False

    async def get(self, timeout: float) -> BookStatusEvent:
        if not self._events:
            raise AssertionError("status stream waited for an unscripted event")
        return self._events.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class ScriptedSubscriber:
    def __init__(self, events: list[BookStatusEvent]) -> None:
        self._events = events
        self.subscription: ScriptedSubscription | None = None

    async def subscribe(self, book_id: str) -> ScriptedSubscription:
        self.subscription = ScriptedSubscription(self._events)
        return self.subscription


def _use(library, subscriber: ScriptedSubscriber) -> None:
    @asynccontextmanager
    async def open_library() -> AsyncGenerator[object, None]:
        yield library

    app.dependency_overrides[get_library_repository_factory] = lambda: open_library
    app.dependency_overrides[get_book_status_subscriber] = lambda: subscriber


def _events(client: TestClient, book_id: str = "book-1") -> list[dict]:
    with client.stream("GET", f"/api/v1/ebooks/{book_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return [
            json.loads(line[len("data: ") :])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]


def test_the_stream_reports_the_current_status_and_then_the_terminal_update() -> None:
    library = ScriptedLibrary(["pending", "processing"])
    subscriber = ScriptedSubscriber([BookStatusEvent("ready")])
    _use(library, subscriber)

    try:
        with TestClient(app) as client:
            events = _events(client)
    finally:
        app.dependency_overrides.pop(get_library_repository_factory, None)
        app.dependency_overrides.pop(get_book_status_subscriber, None)

    assert [event["type"] for event in events] == ["status", "status"]
    assert [event["status"] for event in events] == ["processing", "ready"]
    assert library.reads == 2
    assert subscriber.subscription is not None
    assert subscriber.subscription.closed


def test_the_stream_reports_the_failure_reason_when_processing_fails() -> None:
    library = ScriptedLibrary(["processing", "processing"])
    subscriber = ScriptedSubscriber(
        [BookStatusEvent("failed", error="extraction failed")]
    )
    _use(library, subscriber)

    try:
        with TestClient(app) as client:
            events = _events(client)
    finally:
        app.dependency_overrides.pop(get_library_repository_factory, None)
        app.dependency_overrides.pop(get_book_status_subscriber, None)

    assert events == [
        {"type": "status", "status": "processing", "error": None},
        {"type": "status", "status": "failed", "error": "extraction failed"},
    ]


def test_the_stream_reports_partial_as_a_terminal_status() -> None:
    library = ScriptedLibrary(["partial"])
    subscriber = ScriptedSubscriber([])
    _use(library, subscriber)

    try:
        with TestClient(app) as client:
            events = _events(client)
    finally:
        app.dependency_overrides.pop(get_library_repository_factory, None)
        app.dependency_overrides.pop(get_book_status_subscriber, None)

    assert events == [{"type": "status", "status": "partial", "error": None}]
    assert subscriber.subscription is None


def test_the_stream_reports_an_error_and_closes_when_the_book_is_gone() -> None:
    library = ScriptedLibrary(["processing", None])
    subscriber = ScriptedSubscriber([])
    _use(library, subscriber)

    try:
        with TestClient(app) as client:
            events = _events(client)
    finally:
        app.dependency_overrides.pop(get_library_repository_factory, None)
        app.dependency_overrides.pop(get_book_status_subscriber, None)

    assert events == [{"type": "error", "message": "Book not found"}]
    assert library.reads == 2
    assert subscriber.subscription is not None
    assert subscriber.subscription.closed
