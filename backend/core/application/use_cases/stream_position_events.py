"""Use case for streaming reading-position events for one owned book."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from core.domain.errors import BookNotFoundError
from core.ports.library_repository import LibraryRepository
from core.ports.position_events import PositionEvents


class StreamPositionEventsUseCase:
    def __init__(
        self,
        library: LibraryRepository,
        events: PositionEvents,
    ) -> None:
        self._library = library
        self._events = events

    async def execute(
        self,
        owner_id: str,
        book_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if await self._library.get_book(owner_id, book_id) is None:
            raise BookNotFoundError(book_id)
        return self._events_for(owner_id, book_id)

    async def _events_for(
        self,
        owner_id: str,
        book_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        subscription = await self._events.subscribe(owner_id, book_id)
        try:
            while True:
                yield await subscription.get()
        except asyncio.CancelledError:
            pass
        finally:
            subscription.close()
