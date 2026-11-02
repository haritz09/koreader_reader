import asyncio

from adapters.events.redis_book_status import RedisBookStatusSubscriber


class ScriptedPubSub:
	def __init__(self) -> None:
		self.active = False

	async def subscribe(self, channel: str) -> None:
		self.channel = channel

	async def get_message(self, ignore_subscribe_messages: bool, timeout: float):
		assert ignore_subscribe_messages is False
		self.active = True
		return {"type": "subscribe", "channel": self.channel, "data": 1}

	async def unsubscribe(self, channel: str) -> None:
		pass

	async def aclose(self) -> None:
		pass


class ScriptedRedis:
	def __init__(self) -> None:
		self.pubsub_client = ScriptedPubSub()

	def pubsub(self) -> ScriptedPubSub:
		return self.pubsub_client


def test_subscribe_waits_until_redis_confirms_subscription(monkeypatch) -> None:
	async def _run() -> None:
		redis = ScriptedRedis()
		monkeypatch.setattr(
			"adapters.events.redis_book_status.Redis.from_url",
			lambda *args, **kwargs: redis,
		)
		subscriber = RedisBookStatusSubscriber("redis://localhost")

		subscription = await subscriber.subscribe("book-1")

		assert redis.pubsub_client.active
		await subscription.aclose()

	asyncio.run(_run())
