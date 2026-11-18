"""Use case for streaming one book's processing status."""

from collections.abc import AsyncGenerator

from core.domain.entities.library import LibraryBook
from core.domain.errors import BookNotFoundError
from core.domain.status import TERMINAL_STATUSES
from core.ports.book_status_events import (
    BookStatusEvent,
    BookStatusSubscriber,
    BookStatusSubscription,
)
from core.ports.library_repository import LibraryRepositoryFactory

STATUS_HEARTBEAT_SECONDS = 15.0


class StreamBookStatusUseCase:
    def __init__(
        self,
        open_library: LibraryRepositoryFactory,
        statuses: BookStatusSubscriber,
        heartbeat_seconds: float = STATUS_HEARTBEAT_SECONDS,
    ) -> None:
        self._open_library = open_library
        self._statuses = statuses
        self._heartbeat_seconds = heartbeat_seconds

    async def execute(
        self,
        owner_id: str,
        book_id: str,
    ) -> AsyncGenerator[BookStatusEvent | None, None]:
        async with self._open_library() as library:
            book = await library.get_book(owner_id, book_id)
            if book is None:
                raise BookNotFoundError(book_id)
            if book.processing_status in TERMINAL_STATUSES:
                return _single_event(book)

            subscription = await self._statuses.subscribe(book_id)
            try:
                latest = await library.get_book(owner_id, book_id)
            except Exception:
                await subscription.aclose()
                raise

            if latest is None:
                await subscription.aclose()
                raise BookNotFoundError(book_id)
            if latest.processing_status in TERMINAL_STATUSES:
                await subscription.aclose()
                return _single_event(latest)

        return self._subscription_events(subscription, latest)

    async def _subscription_events(
        self,
        subscription: BookStatusSubscription,
        initial: LibraryBook,
    ) -> AsyncGenerator[BookStatusEvent | None, None]:
        try:
            yield _status_event(initial)
            while True:
                event = await subscription.get(self._heartbeat_seconds)
                if event is None:
                    yield None
                    continue
                yield event
                if event.status in TERMINAL_STATUSES:
                    break
        finally:
            await subscription.aclose()


async def _single_event(book: LibraryBook) -> AsyncGenerator[BookStatusEvent | None, None]:
    yield _status_event(book)


def _status_event(book: LibraryBook) -> BookStatusEvent:
    return BookStatusEvent(
        status=book.processing_status,
        error=book.processing_error,
        chunks_total=book.chunks_total,
        chunks_extracted=book.chunks_extracted,
    )
