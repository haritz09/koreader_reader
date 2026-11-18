import asyncio

import pytest

from core.application.use_cases.browse_library import (
    GetEbookStatusUseCase,
    ListEbooksUseCase,
)
from core.domain.errors import BookNotFoundError


class FakeLibrary:
    def __init__(self, books: list[object]) -> None:
        self.books = books

    async def list_books(self, owner_id: str) -> list[object]:
        return self.books

    async def get_book(self, owner_id: str, book_id: str):
        return self.books[0] if self.books else None


def test_list_returns_the_owners_books() -> None:
    async def _run() -> None:
        books = [object(), object()]
        result = await ListEbooksUseCase(FakeLibrary(books)).execute("owner-1")

        assert result == books

    asyncio.run(_run())


def test_get_returns_the_book_the_owner_can_see() -> None:
    async def _run() -> None:
        book = object()
        result = await GetEbookStatusUseCase(FakeLibrary([book])).execute("owner-1", "book-1")

        assert result is book

    asyncio.run(_run())


def test_get_fails_for_an_unknown_or_unowned_book() -> None:
    async def _run() -> None:
        with pytest.raises(BookNotFoundError):
            await GetEbookStatusUseCase(FakeLibrary([])).execute("owner-1", "book-1")

    asyncio.run(_run())
