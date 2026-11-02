from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BookStatusEvent:
	status: str
	error: str | None = None


class BookStatusPublisher(Protocol):
	async def publish(
		self,
		book_id: str,
		status: str,
		error: str | None = None,
	) -> None: ...

	async def aclose(self) -> None: ...


class BookStatusSubscription(Protocol):
	async def get(self, timeout: float) -> BookStatusEvent | None: ...

	async def aclose(self) -> None: ...


class BookStatusSubscriber(Protocol):
	async def subscribe(self, book_id: str) -> BookStatusSubscription: ...

	async def aclose(self) -> None: ...
