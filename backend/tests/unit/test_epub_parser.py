import asyncio

from adapters.storage.epub_parser import EpubParser
from tests.fixtures.epub import valid_epub_bytes


def test_parser_extracts_ordered_chapters_from_valid_epub(tmp_path) -> None:
	path = tmp_path / "book.epub"
	path.write_bytes(valid_epub_bytes())

	chapters = asyncio.run(EpubParser().parse(str(path)))

	assert [chapter.chapter_id for chapter in chapters] == ["chapter-1", "chapter-2"]
	assert [chapter.chapter_index for chapter in chapters] == [0, 1]
	assert chapters[0].text == "First Opening chapter text."
	assert chapters[1].text == "Second Closing chapter text."