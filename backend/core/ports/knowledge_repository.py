"""Knowledge repository port for spoiler-filtered retrieval."""

from typing import Protocol

from core.domain.entities.knowledge import (
    Entity,
    Event,
    Fact,
    KnowledgeExtractionResult,
    Location,
)


class KnowledgeRepository(Protocol):
    async def insert_batch(
        self,
        book_id: str,
        result: KnowledgeExtractionResult,
    ) -> None: ...

    async def get_entities_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Entity]: ...

    async def get_facts_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Fact]: ...

    async def get_events_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Event]: ...

    async def get_locations_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Location]: ...

    async def delete_by_book(self, book_id: str) -> None: ...
