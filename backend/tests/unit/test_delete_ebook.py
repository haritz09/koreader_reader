import asyncio

import pytest

from core.application.use_cases.delete_ebook import DeleteEbookUseCase
from core.domain.errors import BookNotFoundError, BookProcessingError


class FakeLibraryRepository:
    def __init__(self, book=None) -> None:
        self.book = book
        self.soft_deleted: list[tuple[str, str]] = []

    async def get_book(self, owner_id: str, book_id: str):
        return self.book

    async def soft_delete(self, owner_id: str, book_id: str) -> bool:
        self.soft_deleted.append((owner_id, book_id))
        return True


def book_with_status(status: str):
    return type("Book", (), {"id": "book-1", "processing_status": status})()


def test_delete_marks_the_membership_for_the_caller() -> None:
    library = FakeLibraryRepository(book_with_status("ready"))

    asyncio.run(DeleteEbookUseCase(library).execute("owner-1", "book-1"))

    assert library.soft_deleted == [("owner-1", "book-1")]


def test_delete_rejects_a_book_the_caller_does_not_have() -> None:
    library = FakeLibraryRepository(None)

    with pytest.raises(BookNotFoundError):
        asyncio.run(DeleteEbookUseCase(library).execute("owner-1", "book-1"))

    assert library.soft_deleted == []


def test_delete_rejects_a_book_that_is_still_processing() -> None:
    library = FakeLibraryRepository(book_with_status("processing"))

    with pytest.raises(BookProcessingError):
        asyncio.run(DeleteEbookUseCase(library).execute("owner-1", "book-1"))

    assert library.soft_deleted == []
