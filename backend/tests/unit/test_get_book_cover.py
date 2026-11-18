import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.application.use_cases.get_book_cover import GetBookCoverUseCase
from core.domain.errors import CoverNotFoundError


class FakeLibrary:
    def __init__(self, cover_path: str | None) -> None:
        self.cover_path = cover_path

    async def get_book(self, owner_id: str, book_id: str):
        return SimpleNamespace(cover_path=self.cover_path)


def test_cover_returns_the_stored_path(tmp_path: Path) -> None:
    async def _run() -> None:
        cover = tmp_path / "cover.png"
        cover.write_bytes(b"\x89PNG\r\n\x1a\n")

        result = await GetBookCoverUseCase(FakeLibrary(str(cover))).execute("owner-1", "book-1")

        assert result == cover

    asyncio.run(_run())


def test_cover_fails_when_the_book_has_no_cover() -> None:
    async def _run() -> None:
        with pytest.raises(CoverNotFoundError, match="Cover not found"):
            await GetBookCoverUseCase(FakeLibrary(None)).execute("owner-1", "book-1")

    asyncio.run(_run())


def test_cover_fails_when_the_file_is_missing(tmp_path: Path) -> None:
    async def _run() -> None:
        missing = str(tmp_path / "missing.jpg")

        with pytest.raises(CoverNotFoundError, match="Cover file not found"):
            await GetBookCoverUseCase(FakeLibrary(missing)).execute("owner-1", "book-1")

    asyncio.run(_run())
