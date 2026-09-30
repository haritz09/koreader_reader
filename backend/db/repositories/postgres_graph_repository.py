"""Graph repository implementation for postgres.

This is the anti-spoiler boundary for the graph read path. Both queries apply
``reading_position <= reading_position`` before any row is returned, and the
position is validated so an out-of-range value cannot widen the result to the
whole book.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.graph import EntityMention, FactLink
from core.domain.value_objects.reading_position import validate_reading_position
from db.models.book import Book
from db.models.knowledge import EntityRecord, FactRecord


class PostgresGraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_visible_mentions(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[EntityMention]:
        position = validate_reading_position(reading_position)
        result = await self._session.execute(
            select(
                EntityRecord.id,
                EntityRecord.canonical_id,
                EntityRecord.name,
                EntityRecord.entity_type,
                EntityRecord.reading_position,
            )
            .where(EntityRecord.book_id == book_id)
            .where(EntityRecord.reading_position <= position)
            .order_by(EntityRecord.reading_position, EntityRecord.id)
        )
        return [
            EntityMention(
                entity_id=record_id,
                canonical_id=canonical_id or record_id,
                name=name,
                entity_type=entity_type,
                reading_position=mention_position,
            )
            for record_id, canonical_id, name, entity_type, mention_position in result.all()
        ]

    async def get_visible_facts(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[FactLink]:
        position = validate_reading_position(reading_position)
        result = await self._session.execute(
            select(
                FactRecord.id,
                FactRecord.chunk_id,
                FactRecord.statement,
                FactRecord.subject,
                FactRecord.object,
                FactRecord.reading_position,
            )
            .where(FactRecord.book_id == book_id)
            .where(FactRecord.reading_position <= position)
            .order_by(FactRecord.reading_position, FactRecord.id)
        )
        return [
            FactLink(
                fact_id=fact_id,
                chunk_id=chunk_id,
                statement=statement,
                subject=subject,
                object=object_,
                reading_position=fact_position,
            )
            for fact_id, chunk_id, statement, subject, object_, fact_position in result.all()
        ]

    async def get_revision(self, book_id: str) -> int:
        result = await self._session.execute(
            select(func.coalesce(Book.graph_revision, 0)).where(Book.id == book_id)
        )
        return int(result.scalar_one() or 0)

    async def delete_by_book(self, book_id: str) -> None:
        await self._session.execute(
            EntityRecord.__table__.delete().where(EntityRecord.book_id == book_id)
        )
        await self._session.execute(
            FactRecord.__table__.delete().where(FactRecord.book_id == book_id)
        )
        await self._session.commit()
