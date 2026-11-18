from typing import Any, Protocol


class PositionSubscription(Protocol):
	async def get(self) -> dict[str, Any]: ...

	def close(self) -> None: ...


class PositionEvents(Protocol):
	async def subscribe(
		self,
		owner_id: str,
		book_id: str,
	) -> PositionSubscription: ...
