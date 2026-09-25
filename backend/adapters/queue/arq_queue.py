"""ARQ queue adapter for ebook processing jobs."""

from arq import create_pool
from arq.connections import RedisSettings


class ArqEbookProcessingQueue:
	def __init__(self, redis_url: str) -> None:
		self._redis_settings = RedisSettings.from_dsn(redis_url)

	async def enqueue(self, book_id: str, storage_key: str) -> None:
		redis = await create_pool(self._redis_settings)
		try:
			await redis.enqueue_job(
				"process_ebook",
				book_id=book_id,
				storage_key=storage_key,
			)
		finally:
			await redis.close()