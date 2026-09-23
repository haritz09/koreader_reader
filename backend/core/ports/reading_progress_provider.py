from typing import Protocol


class ReadingProgressProvider(Protocol):
    """Port for importing reading progress from any client or device."""

    def get_progress(self, book_id: str) -> float:
        ...
