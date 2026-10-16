"""Use case for removing a book from one owner's library."""

from core.domain.errors import BookNotFoundError, BookProcessingError
from core.ports.library_repository import LibraryRepository

PROCESSING_STATUS = "processing"


class DeleteEbookUseCase:
    """Soft-delete a book for one owner.

    Book content is shared across owners, so deleting only marks the caller's
    membership as removed. The content is kept for a later purge that runs once
    no owner references the book.
    """

    def __init__(self, library_repository: LibraryRepository) -> None:
        self._library = library_repository

    async def execute(self, owner_id: str, book_id: str) -> None:
        book = await self._library.get_book(owner_id, book_id)
        if book is None:
            raise BookNotFoundError(book_id)
        if book.processing_status == PROCESSING_STATUS:
            raise BookProcessingError(book_id)
        await self._library.soft_delete(owner_id, book_id)
