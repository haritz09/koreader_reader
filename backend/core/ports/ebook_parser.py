from typing import Protocol

from core.domain.entities.chapter import Chapter


class EbookParser(Protocol):
    """Port for extracting chapters and text from ebook files."""

    async def parse(self, storage_path: str) -> list[Chapter]:
        ...
