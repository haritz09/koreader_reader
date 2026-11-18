import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from core.application.use_cases.stream_book_status import StreamBookStatusUseCase
from core.domain.errors import BookNotFoundError
from core.ports.book_status_events import BookStatusEvent


class ScriptedLibrary:
    def __init__(self, books: list[object | None]) -> None:
        self._books = list(books)
        self.reads = 0

    async def get_book(self, owner_id: str, book_id: str):
        self.reads += 1
        return self._books[min(self.reads - 1, len(self._books) - 1)]


class ScriptedSubscription:
    def __init__(self, events: list[BookStatusEvent | None]) -> None:
        self._events = list(events)
        self.timeouts: list[float] = []
        self.closed = False

    async def get(self, timeout: float) -> BookStatusEvent | None:
        self.timeouts.append(timeout)
        if not self._events:
            raise AssertionError("status stream waited for an unscripted event")
        return self._events.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class ScriptedSubscriber:
    def __init__(self, events: list[BookStatusEvent | None]) -> None:
        self._events = events
        self.subscription: ScriptedSubscription | None = None

    async def subscribe(self, book_id: str) -> ScriptedSubscription:
        self.subscription = ScriptedSubscription(self._events)
        return self.subscription


def use_case_for(
    books: list[object | None],
    events: list[BookStatusEvent | None],
) -> tuple[StreamBookStatusUseCase, ScriptedLibrary, ScriptedSubscriber]:
    library = ScriptedLibrary(books)
    subscriber = ScriptedSubscriber(events)

    @asynccontextmanager
    async def open_library():
        yield library

    return StreamBookStatusUseCase(open_library, subscriber), library, subscriber


def a_book(
    status: str,
    *,
    error: str | None = None,
    chunks_total: int = 0,
    chunks_extracted: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        processing_status=status,
        processing_error=error,
        chunks_total=chunks_total,
        chunks_extracted=chunks_extracted,
    )


def test_an_unknown_book_fails_before_the_stream_starts() -> None:
    async def _run() -> None:
        use_case, library, subscriber = use_case_for([None], [])

        with pytest.raises(BookNotFoundError):
            await use_case.execute("owner-1", "book-1")

        assert library.reads == 1
        assert subscriber.subscription is None

    asyncio.run(_run())


def test_a_terminal_book_yields_one_status_event_without_subscribing() -> None:
    async def _run() -> None:
        use_case, _, subscriber = use_case_for([a_book("ready")], [])

        events = await use_case.execute("owner-1", "book-1")
        collected = [event async for event in events]

        assert [(event.status, event.error) for event in collected] == [("ready", None)]
        assert subscriber.subscription is None

    asyncio.run(_run())


def test_the_stream_emits_the_initial_status_and_forwards_progress() -> None:
    async def _run() -> None:
        use_case, _, subscriber = use_case_for(
            [a_book("processing"), a_book("processing")],
            [
                BookStatusEvent("processing", chunks_total=121, chunks_extracted=18),
                BookStatusEvent("ready", chunks_total=121, chunks_extracted=121),
            ],
        )

        events = await use_case.execute("owner-1", "book-1")
        collected = [event async for event in events]

        assert [(event.status, event.chunks_extracted) for event in collected] == [
            ("processing", 0),
            ("processing", 18),
            ("ready", 121),
        ]
        assert subscriber.subscription is not None
        assert subscriber.subscription.closed

    asyncio.run(_run())


def test_a_heartbeat_timeout_is_yielded_as_none_and_the_stream_cleans_up() -> None:
    async def _run() -> None:
        use_case, _, subscriber = use_case_for(
            [a_book("processing"), a_book("processing")],
            [None, BookStatusEvent("failed", error="boom")],
        )

        events = await use_case.execute("owner-1", "book-1")
        collected = [event async for event in events]

        assert collected[0].status == "processing"
        assert collected[1] is None
        assert collected[2].status == "failed"
        assert subscriber.subscription is not None
        assert subscriber.subscription.timeouts == [15.0, 15.0]
        assert subscriber.subscription.closed

    asyncio.run(_run())


def test_a_book_that_disappears_after_subscribing_fails_and_closes() -> None:
    async def _run() -> None:
        use_case, _, subscriber = use_case_for([a_book("processing"), None], [])

        with pytest.raises(BookNotFoundError):
            await use_case.execute("owner-1", "book-1")

        assert subscriber.subscription is not None
        assert subscriber.subscription.closed

    asyncio.run(_run())
