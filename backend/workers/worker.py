"""ARQ worker entrypoint."""

from pathlib import Path

from adapters.storage.epub_parser import EpubParser
from adapters.storage.local_ebook_storage import LocalEbookStorage
from core.config import settings
from core.services.chunking import chunk_chapters
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory


async def process_ebook(ctx: dict, book_id: str, storage_key: str) -> None:
	storage_path = str(Path(settings.ebook_storage_path) / storage_key)
	parser = EpubParser()
	chapters = await parser.parse(storage_path)
	chunks = chunk_chapters(chapters)
	storage = LocalEbookStorage(Path(settings.ebook_storage_path))
	async with session_factory() as session:
		repository = PostgresBookRepository(session)
		await repository.mark_processing(book_id)
		try:
			await repository.replace_derived_content(book_id, chapters, chunks)
			await repository.mark_ready(book_id)
			await storage.delete(storage_key)
		except Exception as error:
			await repository.mark_failed(book_id, str(error))
			raise


class WorkerSettings:
	functions = [process_ebook]
