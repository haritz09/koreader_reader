"""ARQ queue adapter for RAG index jobs."""

from datetime import UTC, datetime, timedelta

from arq import create_pool
from arq.connections import RedisSettings


class ArqRagIndexQueue:
    def __init__(self, redis_url: str) -> None:
        self._redis_settings = RedisSettings.from_dsn(redis_url)

    async def enqueue(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        *,
        defer_by_seconds: float | None = None,
    ) -> None:
        redis = await create_pool(self._redis_settings)
        try:
            job_id = f"rag:{book_id}:{graph_revision}:{embedding_model}"
            if defer_by_seconds is not None:
                job_id = f"{job_id}:retry:{int(datetime.now(UTC).timestamp())}"
            await redis.enqueue_job(
                "build_rag_index",
                book_id=book_id,
                _job_id=job_id,
                _defer_by=(
                    timedelta(seconds=defer_by_seconds)
                    if defer_by_seconds is not None
                    else None
                ),
            )
        finally:
            await redis.close()
