import asyncio
import json

from adapters.events.redis_book_status import (
    RedisBookStatusPublisher,
    RedisBookStatusSubscriber,
)


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


class RecordingRedis:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> None:
        self.messages.append((channel, payload))

    async def aclose(self) -> None:
        pass


def test_publisher_reports_extraction_progress_only_when_known(monkeypatch) -> None:
    async def _run() -> None:
        redis = RecordingRedis()
        monkeypatch.setattr(
            "adapters.events.redis_book_status.Redis.from_url",
            lambda *args, **kwargs: redis,
        )
        publisher = RedisBookStatusPublisher("redis://localhost")

        await publisher.publish("book-1", "processing", chunks_total=10, chunks_extracted=4)
        await publisher.publish("book-1", "ready")
        await publisher.aclose()

        assert [json.loads(payload) for _, payload in redis.messages] == [
            {
                "status": "processing",
                "error": None,
                "chunks_total": 10,
                "chunks_extracted": 4,
            },
            {"status": "ready", "error": None},
        ]

    asyncio.run(_run())
