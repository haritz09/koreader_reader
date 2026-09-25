"""Local filesystem storage for uploaded EPUB files."""

import asyncio
from pathlib import Path


class LocalEbookStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, storage_key: str, content: bytes) -> str:
        path = self._root / storage_key
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        return str(path)

    async def delete(self, storage_key: str) -> None:
        path = self._root / storage_key
        await asyncio.to_thread(path.unlink, missing_ok=True)