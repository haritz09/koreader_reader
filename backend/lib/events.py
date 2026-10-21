"""In-process event bus for SSE notifications."""

import asyncio
from collections import defaultdict
from typing import Any

_subscribers: dict[tuple[str, str], list[asyncio.Queue]] = defaultdict(list)


async def publish(owner_id: str, book_id: str, event: dict[str, Any]) -> None:
	for queue in _subscribers.get((owner_id, book_id), []):
		await queue.put(event)


async def subscribe(owner_id: str, book_id: str) -> asyncio.Queue:
	queue: asyncio.Queue = asyncio.Queue()
	_subscribers[(owner_id, book_id)].append(queue)
	return queue


def unsubscribe(owner_id: str, book_id: str, queue: asyncio.Queue) -> None:
	key = (owner_id, book_id)
	if key in _subscribers:
		_subscribers[key] = [q for q in _subscribers[key] if q is not queue]
