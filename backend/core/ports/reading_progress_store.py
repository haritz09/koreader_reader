from typing import Protocol


class ReadingProgressStore(Protocol):
    async def update_progress(self, book_id: str, position: float) -> None:
        ...
