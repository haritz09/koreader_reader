"""In-process position-event broker adapter."""

from typing import Any

import lib.events
from core.ports.position_events import PositionSubscription


class InMemoryPositionSubscription:
	def __init__(self, owner_id: str, book_id: str, queue: Any) -> None:
		self._owner_id = owner_id
		self._book_id = book_id
		self._queue = queue

	async def get(self) -> dict[str, Any]:
		return await self._queue.get()

	def close(self) -> None:
		lib.events.unsubscribe(self._owner_id, self._book_id, self._queue)


class InMemoryPositionEvents:
	async def subscribe(
		self,
		owner_id: str,
		book_id: str,
	) -> PositionSubscription:
		queue = await lib.events.subscribe(owner_id, book_id)
		return InMemoryPositionSubscription(owner_id, book_id, queue)
