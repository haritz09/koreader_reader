"""Knowledge and spoiler-filtered retrieval repository."""

from collections.abc import Mapping

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.graph import EntityCandidate
from core.domain.entities.knowledge import (
    Entity,
    Event,
    Fact,
    KnowledgeExtractionResult,
    Location,
)
from core.domain.value_objects.reading_position import validate_reading_position
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
            .where(EntityRecord.reading_position <= validate_reading_position(reading_position))
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
            .where(FactRecord.reading_position <= validate_reading_position(reading_position))
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
            .where(EventRecord.reading_position <= validate_reading_position(reading_position))
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
            .where(LocationRecord.reading_position <= validate_reading_position(reading_position))
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

    async def get_entity_candidates(self, book_id: str) -> list[EntityCandidate]:
        """Return every mention for identity grouping.

        Intentionally unfiltered: the mapping is a position-independent pointer
        to a canonical row, never a label, so resolving ahead of the reader
        cannot disclose anything. Labels are derived from visible mentions in
        the graph assembly service.
        """
        result = await self._session.execute(
            select(
                EntityRecord.id,
                EntityRecord.name,
                EntityRecord.entity_type,
                EntityRecord.reading_position,
            )
            .where(EntityRecord.book_id == book_id)
            .order_by(EntityRecord.reading_position, EntityRecord.id)
        )
        return [
            EntityCandidate(
                entity_id=record_id,
                name=name,
                entity_type=entity_type,
                reading_position=reading_position,
            )
            for record_id, name, entity_type, reading_position in result.all()
        ]

    async def get_resolution(
        self, book_id: str
    ) -> Mapping[str, tuple[str | None, str | None]]:
        result = await self._session.execute(
            select(
                EntityRecord.id,
                EntityRecord.canonical_id,
                EntityRecord.resolution_method,
            ).where(EntityRecord.book_id == book_id)
        )
        return {record_id: (canonical_id, method) for record_id, canonical_id, method in result.all()}

    async def apply_resolution(
        self,
        book_id: str,
        canonical_by_entity: Mapping[str, str],
        method_by_entity: Mapping[str, str],
    ) -> None:
        if not canonical_by_entity:
            return
        entity_ids = list(canonical_by_entity)
        await self._session.execute(
            update(EntityRecord)
            .where(EntityRecord.book_id == book_id)
            .where(EntityRecord.id.in_(entity_ids))
            .values(
                canonical_id=case(
                    dict(canonical_by_entity),
                    value=EntityRecord.id,
                ),
                resolution_method=case(
                    {entity_id: method_by_entity.get(entity_id) for entity_id in entity_ids},
                    value=EntityRecord.id,
                ),
            )
        )
        await self._session.commit()

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
