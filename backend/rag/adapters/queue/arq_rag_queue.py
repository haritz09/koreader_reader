"""ARQ queue adapter for RAG index jobs."""

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
    ) -> None:
        redis = await create_pool(self._redis_settings)
        try:
            await redis.enqueue_job(
                "build_rag_index",
                book_id=book_id,
                _job_id=f"rag:{book_id}:{graph_revision}:{embedding_model}",
            )
        finally:
            await redis.close()
