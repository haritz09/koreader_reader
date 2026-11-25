"""PostgreSQL retrieval over stored embeddings."""

from collections.abc import Sequence

from sqlalchemy import Row, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects.reading_position import ReadingPosition
from db.models.chunk import ChunkRecord
from db.models.knowledge import EntityRecord
from rag.adapters.persistence.models import RagEmbeddingRecord
from rag.domain.embeddings import EmbeddingSourceType
from rag.domain.retrieval import KnowledgeHit, RetrievedChunk

OVERFETCH_FACTOR = 4
MAX_CANDIDATES = 100


class PostgresRetrievalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_chunks(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        position_value = float(ReadingPosition(position))
        if limit <= 0:
            return []

        distance = RagEmbeddingRecord.embedding.cosine_distance(list(query_embedding)).label(
            "distance"
        )
        result = await self._session.execute(
            select(
                RagEmbeddingRecord.chunk_id,
                RagEmbeddingRecord.reading_position,
                ChunkRecord.chunk_index,
                ChunkRecord.text,
                distance,
            )
            .join(ChunkRecord, ChunkRecord.id == RagEmbeddingRecord.chunk_id)
            .where(
                RagEmbeddingRecord.book_id == book_id,
                RagEmbeddingRecord.model == model,
                RagEmbeddingRecord.reading_position <= position_value,
                RagEmbeddingRecord.chunk_id.is_not(None),
            )
            .order_by(distance)
            .limit(min(limit * OVERFETCH_FACTOR, MAX_CANDIDATES))
        )
        return _best_per_chunk(result.all(), limit)

    async def search_knowledge(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[KnowledgeHit]:
        position_value = float(ReadingPosition(position))
        if limit <= 0:
            return []

        distance = RagEmbeddingRecord.embedding.cosine_distance(list(query_embedding)).label(
            "distance"
        )
        result = await self._session.execute(
            select(
                RagEmbeddingRecord.reading_position,
                ChunkRecord.id.label("chunk_id"),
                ChunkRecord.chunk_index,
                ChunkRecord.text,
                EntityRecord.canonical_id,
                distance,
            )
            .join(ChunkRecord, ChunkRecord.id == RagEmbeddingRecord.chunk_id)
            .outerjoin(
                EntityRecord,
                and_(
                    EntityRecord.id == RagEmbeddingRecord.source_id,
                    RagEmbeddingRecord.source_type == EmbeddingSourceType.ENTITY.value,
                ),
            )
            .where(
                RagEmbeddingRecord.book_id == book_id,
                RagEmbeddingRecord.model == model,
                RagEmbeddingRecord.reading_position <= position_value,
                RagEmbeddingRecord.source_type != EmbeddingSourceType.CHUNK.value,
            )
            .order_by(distance)
            .limit(min(limit * OVERFETCH_FACTOR, MAX_CANDIDATES))
        )
        return _best_knowledge_per_chunk(result.all(), limit)

    async def expand_entity_chunks(
        self,
        book_id: str,
        position: float,
        canonical_ids: Sequence[str],
        limit: int,
    ) -> list[RetrievedChunk]:
        position_value = float(ReadingPosition(position))
        if limit <= 0 or not canonical_ids:
            return []

        result = await self._session.execute(
            select(
                EntityRecord.chunk_id,
                ChunkRecord.chunk_index,
                ChunkRecord.text,
                EntityRecord.reading_position,
            )
            .join(ChunkRecord, ChunkRecord.id == EntityRecord.chunk_id)
            .where(
                EntityRecord.book_id == book_id,
                EntityRecord.reading_position <= position_value,
                or_(
                    EntityRecord.canonical_id.in_(list(canonical_ids)),
                    EntityRecord.id.in_(list(canonical_ids)),
                ),
            )
            .order_by(EntityRecord.reading_position, EntityRecord.id)
            .limit(limit)
        )
        seen: dict[str, RetrievedChunk] = {}
        for chunk_id, chunk_index, text, reading_position in result.all():
            seen.setdefault(
                chunk_id,
                RetrievedChunk(
                    chunk_id=chunk_id,
                    chunk_index=chunk_index,
                    reading_position=reading_position,
                    distance=1.0,
                    text=text,
                ),
            )
        return list(seen.values())


def _best_per_chunk(rows: Sequence[Row], limit: int) -> list[RetrievedChunk]:
    best: dict[str, RetrievedChunk] = {}
    for row in rows:
        if row.chunk_id is None:
            continue
        best.setdefault(
            row.chunk_id,
            RetrievedChunk(
                chunk_id=row.chunk_id,
                chunk_index=row.chunk_index,
                reading_position=row.reading_position,
                distance=float(row.distance),
                text=row.text,
            ),
        )
    return list(best.values())[:limit]


def _best_knowledge_per_chunk(rows: Sequence[Row], limit: int) -> list[KnowledgeHit]:
    best: dict[str, KnowledgeHit] = {}
    for row in rows:
        best.setdefault(
            row.chunk_id,
            KnowledgeHit(
                chunk=RetrievedChunk(
                    chunk_id=row.chunk_id,
                    chunk_index=row.chunk_index,
                    reading_position=row.reading_position,
                    distance=float(row.distance),
                    text=row.text,
                ),
                canonical_id=row.canonical_id,
            ),
        )
    return list(best.values())[:limit]
