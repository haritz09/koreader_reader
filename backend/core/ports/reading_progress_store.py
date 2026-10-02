from typing import Protocol

from core.domain.entities.graph import BookGraphState


class ReadingProgressStore(Protocol):
    async def update_progress(self, book_id: str, position: float) -> None:
        ...

    async def get_graph_state(self, book_id: str) -> BookGraphState | None:
        ...
