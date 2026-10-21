from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from core.domain.entities.library import LibraryBook, ReadingState


class LibraryRepository(Protocol):
    """Owns the per-owner membership rows over shared book content."""

    async def link(self, owner_id: str, book_id: str) -> None:
        ...

    async def get_book(self, owner_id: str, book_id: str) -> LibraryBook | None:
        ...

    async def list_books(self, owner_id: str) -> list[LibraryBook]:
        ...

    async def soft_delete(self, owner_id: str, book_id: str) -> bool:
        ...

    async def get_reading_state(
        self, owner_id: str, book_id: str
    ) -> ReadingState | None:
        ...

    async def update_progress(
        self,
        owner_id: str,
        book_id: str,
        position: float,
        synced_at: datetime,
    ) -> bool:
        ...


class LibraryRepositoryFactory(Protocol):
    """Opens a library repository whose session lives as long as a stream."""

    def __call__(self) -> AbstractAsyncContextManager[LibraryRepository]:
        ...
