"""Redis pub/sub bridge for worker-owned processing status."""

import json

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from core.ports.book_status_events import BookStatusEvent

_CHANNEL_PREFIX = "book-status:"


def _channel(book_id: str) -> str:
	return f"{_CHANNEL_PREFIX}{book_id}"


class RedisBookStatusPublisher:
	def __init__(self, redis_url: str) -> None:
		self._redis = Redis.from_url(redis_url)

	async def publish(
		self,
		book_id: str,
		status: str,
		error: str | None = None,
	) -> None:
		await self._redis.publish(
			_channel(book_id),
			json.dumps({"status": status, "error": error}),
		)

	async def aclose(self) -> None:
		await self._redis.aclose()


class RedisBookStatusSubscription:
	def __init__(self, pubsub: PubSub, channel: str) -> None:
		self._pubsub = pubsub
		self._channel = channel
		self._closed = False

	async def get(self, timeout: float) -> BookStatusEvent | None:
		message = await self._pubsub.get_message(
			ignore_subscribe_messages=True,
			timeout=timeout,
		)
		if message is None:
			return None
		data = message.get("data")
		if not isinstance(data, str):
			return None
		try:
			payload = json.loads(data)
		except (TypeError, ValueError):
			return None
		if not isinstance(payload, dict):
			return None
		status = payload.get("status")
		if not isinstance(status, str):
			return None
		error = payload.get("error")
		return BookStatusEvent(
			status=status,
			error=error if isinstance(error, str) else None,
		)

	async def aclose(self) -> None:
		if self._closed:
			return
		self._closed = True
		await self._pubsub.unsubscribe(self._channel)
		await self._pubsub.aclose()


class RedisBookStatusSubscriber:
	def __init__(self, redis_url: str) -> None:
		self._redis = Redis.from_url(redis_url, decode_responses=True)

	async def subscribe(self, book_id: str) -> RedisBookStatusSubscription:
		pubsub = self._redis.pubsub()
		channel = _channel(book_id)
		try:
			await pubsub.subscribe(channel)
			acknowledgement = await pubsub.get_message(
				ignore_subscribe_messages=False,
				timeout=1.0,
			)
			if (
				acknowledgement is None
				or acknowledgement.get("type") != "subscribe"
				or acknowledgement.get("channel") != channel
			):
				raise RuntimeError(f"Redis did not confirm subscription to {channel}")
		except Exception:
			await pubsub.aclose()
			raise
		return RedisBookStatusSubscription(pubsub, channel)

	async def aclose(self) -> None:
		await self._redis.aclose()
