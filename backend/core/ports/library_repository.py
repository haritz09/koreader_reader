from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol


class LibraryRepository(Protocol):
    """Owns the per-owner membership rows over shared book content."""

    async def link(self, owner_id: str, book_id: str) -> None:
        ...

    async def get_book(self, owner_id: str, book_id: str) -> Any | None:
        ...

    async def list_books(self, owner_id: str) -> list[Any]:
        ...

    async def soft_delete(self, owner_id: str, book_id: str) -> bool:
        ...


class LibraryRepositoryFactory(Protocol):
    """Opens a library repository whose session lives as long as a stream."""

    def __call__(self) -> AbstractAsyncContextManager[LibraryRepository]:
        ...
