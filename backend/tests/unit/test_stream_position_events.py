import asyncio

import pytest

from core.application.use_cases.stream_position_events import (
    StreamPositionEventsUseCase,
)
from core.domain.errors import BookNotFoundError


class FakeLibrary:
    def __init__(self, owned: bool = True) -> None:
        self.owned = owned

    async def get_book(self, owner_id: str, book_id: str):
        return object() if self.owned else None


class FakeSubscription:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self._events = list(events)
        self.closed = False

    async def get(self) -> dict[str, object]:
        return self._events.pop(0)

    def close(self) -> None:
        self.closed = True


class FakeEvents:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self._events = events
        self.subscribed: tuple[str, str] | None = None
        self.subscription: FakeSubscription | None = None

    async def subscribe(self, owner_id: str, book_id: str) -> FakeSubscription:
        self.subscribed = (owner_id, book_id)
        self.subscription = FakeSubscription(self._events)
        return self.subscription


def test_an_unknown_book_fails_before_subscribing() -> None:
    async def _run() -> None:
        events = FakeEvents([])
        use_case = StreamPositionEventsUseCase(FakeLibrary(owned=False), events)

        with pytest.raises(BookNotFoundError):
            await use_case.execute("owner-1", "book-1")

        assert events.subscribed is None

    asyncio.run(_run())


def test_closing_the_stream_unsubscribes() -> None:
    async def _run() -> None:
        events = FakeEvents([{"book_id": "book-1", "position": 0.5}])
        use_case = StreamPositionEventsUseCase(FakeLibrary(), events)

        stream = await use_case.execute("owner-1", "book-1")
        event = await stream.__anext__()
        await stream.aclose()

        assert event == {"book_id": "book-1", "position": 0.5}
        assert events.subscribed == ("owner-1", "book-1")
        assert events.subscription is not None
        assert events.subscription.closed

    asyncio.run(_run())
