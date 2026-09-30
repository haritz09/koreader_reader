"""ARQ queue adapter for graph generation jobs."""

from arq import create_pool
from arq.connections import RedisSettings


class ArqGraphGenerationQueue:
    def __init__(self, redis_url: str) -> None:
        self._redis_settings = RedisSettings.from_dsn(redis_url)

    async def enqueue(self, book_id: str) -> None:
        redis = await create_pool(self._redis_settings)
        try:
            await redis.enqueue_job("generate_graph", book_id=book_id)
        finally:
            await redis.close()
