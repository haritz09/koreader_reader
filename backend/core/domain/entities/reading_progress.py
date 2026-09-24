from dataclasses import dataclass


@dataclass(frozen=True)
class ReadingProgress:
    book_id: str
    position: float