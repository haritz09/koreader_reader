"""Library and reading-state entities."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LibraryBook:
    """One active membership joined with the content it points at."""

    book_id: str
    document_hash: str
    processing_status: str
    processing_error: str | None
    cover_path: str | None
    progress_position: float
    added_at: datetime
    last_synced_at: datetime | None


@dataclass(frozen=True)
class ReadingState:
    """The per-owner position plus the shared processing facts around it."""

    progress_position: float
    last_synced_at: datetime | None
    processing_status: str
    graph_revision: int
