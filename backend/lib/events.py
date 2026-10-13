"""In-process event bus for SSE notifications."""

import asyncio
from collections import defaultdict
from typing import Any

_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def publish(book_id: str, event: dict[str, Any]) -> None:
	for queue in _subscribers.get(book_id, []):
		await queue.put(event)


async def subscribe(book_id: str) -> asyncio.Queue:
	queue: asyncio.Queue = asyncio.Queue()
	_subscribers[book_id].append(queue)
	return queue


def unsubscribe(book_id: str, queue: asyncio.Queue) -> None:
	if book_id in _subscribers:
		_subscribers[book_id] = [q for q in _subscribers[book_id] if q is not queue]
