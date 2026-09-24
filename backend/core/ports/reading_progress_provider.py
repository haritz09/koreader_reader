from typing import Protocol

from core.domain.entities.reading_progress import ReadingProgress


class ReadingProgressProvider(Protocol):
    """Port for resolving client-specific progress into domain progress."""

    async def resolve_progress(
        self,
        document_hash: str,
        position: float,
    ) -> ReadingProgress | None:
        ...
