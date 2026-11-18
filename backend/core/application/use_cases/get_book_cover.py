from pathlib import Path

from core.domain.errors import CoverNotFoundError
from core.ports.library_repository import LibraryRepository


class GetBookCoverUseCase:
    def __init__(self, library: LibraryRepository) -> None:
        self._library = library

    async def execute(self, owner_id: str, book_id: str) -> Path:
        book = await self._library.get_book(owner_id, book_id)
        if book is None or not book.cover_path:
            raise CoverNotFoundError("Cover not found")
        cover_path = Path(book.cover_path)
        if not cover_path.exists():
            raise CoverNotFoundError("Cover file not found")
        return cover_path
