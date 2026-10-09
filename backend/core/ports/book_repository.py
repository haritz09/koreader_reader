from typing import Any, Protocol

from core.domain.entities.chapter import Chapter
from core.domain.entities.chunk import Chunk
from core.domain.entities.graph import BookGraphState


class BookRepository(Protocol):
    async def resolve_book_id(self, document_hash: str) -> str | None:
        ...

    async def get_by_document_hash(self, document_hash: str) -> Any | None:
        ...

    async def create(
        self,
        book_id: str,
        document_hash: str,
        storage_key: str,
    ) -> Any:
        ...

    async def get_by_id(self, book_id: str) -> Any | None:
        ...

    async def update_progress(self, book_id: str, position: float) -> None:
        ...

    async def mark_processing(self, book_id: str) -> None:
        ...

    async def replace_derived_content(
        self,
        book_id: str,
        chapters: list[Chapter],
        chunks: list[Chunk],
    ) -> None:
        ...

    async def mark_ready(self, book_id: str) -> None:
        ...

    async def mark_failed(self, book_id: str, error: str) -> None:
        ...

    async def get_chunk_ids_by_book(self, book_id: str) -> list[tuple[str, int]]:
        ...

    async def get_graph_state(self, book_id: str) -> BookGraphState | None:
        ...

    async def bump_graph_revision(self, book_id: str) -> int:
        ...

    async def list_all(self) -> list[Any]:
        ...

    async def set_cover_path(self, book_id: str, cover_path: str) -> None:
        ...
