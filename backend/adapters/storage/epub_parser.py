"""EPUB parser adapter using EbookLib and BeautifulSoup."""

import asyncio

from bs4 import BeautifulSoup
from ebooklib import epub, ITEM_DOCUMENT

from core.domain.entities.chapter import Chapter


class EpubParser:
	async def parse(self, storage_path: str) -> list[Chapter]:
		return await asyncio.to_thread(self._parse_sync, storage_path)

	@staticmethod
	def _parse_sync(storage_path: str) -> list[Chapter]:
		book = epub.read_epub(storage_path)
		chapters: list[Chapter] = []
		for chapter_index, item in enumerate(book.get_items_of_type(ITEM_DOCUMENT)):
			soup = BeautifulSoup(item.get_content(), "html.parser")
			text = " ".join(soup.stripped_strings)
			if not text:
				continue
			chapters.append(
				Chapter(
					chapter_id=item.get_id(),
					title=text.split(" ", 1)[0][:120],
					text=text,
					chapter_index=chapter_index,
				)
			)
		return chapters
