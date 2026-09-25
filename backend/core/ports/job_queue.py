from typing import Protocol


class EbookProcessingQueue(Protocol):
    async def enqueue(self, book_id: str, storage_key: str) -> None:
        ...