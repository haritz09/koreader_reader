"""Graph repository implementation for postgres.

Anti-spoiler boundary for the graph read path: every query filters
``reading_position <= position`` and validates the position first, so an
out-of-range value cannot widen the result to the whole book. Places and
events live in their own tables and are read through the same filter.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.graph import EntityMention, FactLink
from core.domain.entities.knowledge import EVENT_NODE_TYPE, LOCATION_NODE_TYPE
from core.domain.value_objects.reading_position import validate_reading_position
from db.models.book import Book
from db.models.knowledge import EntityRecord, EventRecord, FactRecord, LocationRecord


class PostgresGraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_visible_mentions(
        self,
        book_id: str,
        reading_position: float,
    ) -> list[EntityMention]:
        position = validate_reading_position(reading_position)
        mentions: list[EntityMention] = await self._entity_mentions(book_id, position)
        mentions.extend(
            await self._standalone_mentions(book_id, position, LocationRecord, LOCATION_NODE_TYPE)
        )
        mentions.extend(
            await self._standalone_mentions(book_id, position, EventRecord, EVENT_NODE_TYPE)
        )
        mentions.sort(key=lambda mention: (mention.reading_position, mention.entity_id))
        return mentions

    async def _entity_mentions(
        self, book_id: str, position: float
    ) -> list[EntityMention]:
        result = await self._session.execute(
            select(
                EntityRecord.id,
                EntityRecord.canonical_id,
                EntityRecord.name,
                EntityRecord.entity_type,
                EntityRecord.description,
                EntityRecord.sub_type,
                EntityRecord.aliases,
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
                description=description or "",
                sub_type=sub_type,
                aliases=tuple(aliases or ()),
            )
            for (
                record_id,
                canonical_id,
                name,
                entity_type,
                description,
                sub_type,
                aliases,
                mention_position,
            ) in result.all()
        ]

    async def _standalone_mentions(
        self,
        book_id: str,
        position: float,
        table,
        node_type: str,
    ) -> list[EntityMention]:
        """Read places and events, which carry no canonical pointer of their own."""
        result = await self._session.execute(
            select(table.id, table.name, table.description, table.reading_position)
            .where(table.book_id == book_id)
            .where(table.reading_position <= position)
            .order_by(table.reading_position, table.id)
        )
        return [
            EntityMention(
                entity_id=record_id,
                canonical_id=record_id,
                name=name,
                entity_type=node_type,
                reading_position=mention_position,
                description=description or "",
            )
            for record_id, name, description, mention_position in result.all()
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
        for table in (EntityRecord, FactRecord, EventRecord, LocationRecord):
            await self._session.execute(
                table.__table__.delete().where(table.book_id == book_id)
            )
        await self._session.commit()
