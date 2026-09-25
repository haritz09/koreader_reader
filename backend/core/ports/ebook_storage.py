from typing import Protocol


class EbookStorage(Protocol):
    async def save(self, storage_key: str, content: bytes) -> str:
        ...

    async def delete(self, storage_key: str) -> None:
        ...