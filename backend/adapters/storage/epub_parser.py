"""EPUB parser adapter using EbookLib and BeautifulSoup."""

import asyncio

from bs4 import BeautifulSoup
from ebooklib import ITEM_COVER, ITEM_DOCUMENT, ITEM_IMAGE, epub

from core.domain.entities.chapter import Chapter


class EpubParser:
	async def parse(self, storage_path: str) -> list[Chapter]:
		return await asyncio.to_thread(self._parse_sync, storage_path)

	async def extract_cover(self, storage_path: str) -> bytes | None:
		return await asyncio.to_thread(self._extract_cover_sync, storage_path)

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

	@staticmethod
	def _extract_cover_sync(storage_path: str) -> bytes | None:
		book = epub.read_epub(storage_path)
		for item in book.get_items_of_type(ITEM_COVER):
			content = item.get_content()
			if content:
				return content
		for item in book.get_items_of_type(ITEM_IMAGE):
			if "cover" in item.get_name().lower():
				content = item.get_content()
				if content:
					return content
		return None
