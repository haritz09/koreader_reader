from typing import Protocol


class BookRepository(Protocol):
    async def resolve_book_id(self, document_hash: str) -> str | None:
        ...