"""Graph repository port for spoiler-filtered graph reads.

Implementations must apply ``reading_position <= reading_position`` themselves.
Returning unfiltered rows and filtering in the service would move the
anti-spoiler boundary out of the data-access layer.
"""

from typing import Protocol

from core.domain.entities.graph import EntityMention, FactLink


class GraphRepository(Protocol):
    async def get_visible_mentions(
        self, book_id: str, reading_position: float
    ) -> list[EntityMention]: ...

    async def get_visible_facts(
        self, book_id: str, reading_position: float
    ) -> list[FactLink]: ...

    async def get_revision(self, book_id: str) -> int: ...

    async def delete_by_book(self, book_id: str) -> None: ...
