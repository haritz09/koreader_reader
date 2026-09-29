"""Knowledge and spoiler-filtered retrieval repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.knowledge import (
    Entity,
    Event,
    Fact,
    KnowledgeExtractionResult,
    Location,
)
from db.models.knowledge import EntityRecord, EventRecord, FactRecord, LocationRecord


class PostgresKnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_batch(
        self,
        book_id: str,
        result: KnowledgeExtractionResult,
    ) -> None:
        self._session.add_all(
            EntityRecord(
                id=e.entity_id,
                book_id=e.book_id,
                chunk_id=e.chunk_id,
                name=e.name,
                entity_type=e.entity_type,
                reading_position=e.reading_position,
            )
            for e in result.entities
        )
        self._session.add_all(
            FactRecord(
                id=f.fact_id,
                book_id=f.book_id,
                chunk_id=f.chunk_id,
                statement=f.statement,
                subject=f.subject,
                object=f.object,
                reading_position=f.reading_position,
            )
            for f in result.facts
        )
        self._session.add_all(
            EventRecord(
                id=ev.event_id,
                book_id=ev.book_id,
                chunk_id=ev.chunk_id,
                description=ev.description,
                reading_position=ev.reading_position,
            )
            for ev in result.events
        )
        self._session.add_all(
            LocationRecord(
                id=loc.location_id,
                book_id=loc.book_id,
                chunk_id=loc.chunk_id,
                name=loc.name,
                description=loc.description,
                reading_position=loc.reading_position,
            )
            for loc in result.locations
        )
        await self._session.commit()

    async def get_entities_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Entity]:
        result = await self._session.execute(
            select(EntityRecord)
            .where(EntityRecord.book_id == book_id)
            .where(EntityRecord.reading_position <= reading_position)
            .order_by(EntityRecord.reading_position)
        )
        return [
            Entity(
                entity_id=r.id,
                book_id=r.book_id,
                chunk_id=r.chunk_id,
                name=r.name,
                entity_type=r.entity_type,
                reading_position=r.reading_position,
            )
            for r in result.scalars()
        ]

    async def get_facts_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Fact]:
        result = await self._session.execute(
            select(FactRecord)
            .where(FactRecord.book_id == book_id)
            .where(FactRecord.reading_position <= reading_position)
            .order_by(FactRecord.reading_position)
        )
        return [
            Fact(
                fact_id=r.id,
                book_id=r.book_id,
                chunk_id=r.chunk_id,
                statement=r.statement,
                subject=r.subject,
                object=r.object,
                reading_position=r.reading_position,
            )
            for r in result.scalars()
        ]

    async def get_events_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Event]:
        result = await self._session.execute(
            select(EventRecord)
            .where(EventRecord.book_id == book_id)
            .where(EventRecord.reading_position <= reading_position)
            .order_by(EventRecord.reading_position)
        )
        return [
            Event(
                event_id=r.id,
                book_id=r.book_id,
                chunk_id=r.chunk_id,
                description=r.description,
                reading_position=r.reading_position,
            )
            for r in result.scalars()
        ]

    async def get_locations_by_book(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[Location]:
        result = await self._session.execute(
            select(LocationRecord)
            .where(LocationRecord.book_id == book_id)
            .where(LocationRecord.reading_position <= reading_position)
            .order_by(LocationRecord.reading_position)
        )
        return [
            Location(
                location_id=r.id,
                book_id=r.book_id,
                chunk_id=r.chunk_id,
                name=r.name,
                description=r.description,
                reading_position=r.reading_position,
            )
            for r in result.scalars()
        ]

    async def delete_by_book(self, book_id: str) -> None:
        await self._session.execute(
            EntityRecord.__table__.delete().where(EntityRecord.book_id == book_id)
        )
        await self._session.execute(
            FactRecord.__table__.delete().where(FactRecord.book_id == book_id)
        )
        await self._session.execute(
            EventRecord.__table__.delete().where(EventRecord.book_id == book_id)
        )
        await self._session.execute(
            LocationRecord.__table__.delete().where(LocationRecord.book_id == book_id)
        )
        await self._session.commit()
