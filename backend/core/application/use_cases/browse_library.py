"""Use cases for reading the caller's library."""

from core.domain.entities.library import LibraryBook
from core.domain.errors import BookNotFoundError
from core.ports.library_repository import LibraryRepository


class ListEbooksUseCase:
    def __init__(self, library: LibraryRepository) -> None:
        self._library = library

    async def execute(self, owner_id: str) -> list[LibraryBook]:
        return await self._library.list_books(owner_id)


class GetEbookStatusUseCase:
    def __init__(self, library: LibraryRepository) -> None:
        self._library = library

    async def execute(self, owner_id: str, book_id: str) -> LibraryBook:
        book = await self._library.get_book(owner_id, book_id)
        if book is None:
            raise BookNotFoundError(book_id)
        return book
