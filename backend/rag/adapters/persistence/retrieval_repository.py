"""PostgreSQL retrieval over stored embeddings."""

from collections.abc import Sequence

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects.reading_position import ReadingPosition
from db.models.chunk import ChunkRecord
from rag.adapters.persistence.models import RagEmbeddingRecord
from rag.domain.retrieval import RetrievedChunk

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

        distance = RagEmbeddingRecord.embedding.cosine_distance(
            list(query_embedding)
        ).label("distance")
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
