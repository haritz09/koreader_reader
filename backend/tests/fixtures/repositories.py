"""Library repository fakes shared by unit and contract tests."""

from collections.abc import Collection
from dataclasses import replace
from datetime import datetime

from core.domain.entities.library import ReadingState


def reading_state(
    progress_position: float = 0.0,
    processing_status: str = "ready",
    graph_revision: int = 0,
    last_synced_at: datetime | None = None,
) -> ReadingState:
    return ReadingState(
        progress_position=progress_position,
        last_synced_at=last_synced_at,
        processing_status=processing_status,
        graph_revision=graph_revision,
    )


class FakeLibraryRepository:
    def __init__(
        self,
        state: ReadingState | None = None,
        known_book_ids: Collection[str] | None = None,
    ) -> None:
        self.state = state
        self.known_book_ids = (
            None if known_book_ids is None else set(known_book_ids)
        )
        self.updates: list[tuple[str, float]] = []

    async def get_reading_state(
        self, owner_id: str, book_id: str
    ) -> ReadingState | None:
        return self.state if self._knows(book_id) else None

    async def update_progress(
        self,
        owner_id: str,
        book_id: str,
        position: float,
        synced_at: datetime,
    ) -> bool:
        if not self._knows(book_id) or self.state is None:
            return False
        self.updates.append((book_id, position))
        self.state = replace(
            self.state,
            progress_position=position,
            last_synced_at=synced_at,
        )
        return True

    def _knows(self, book_id: str) -> bool:
        return self.known_book_ids is None or book_id in self.known_book_ids
