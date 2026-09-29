"""ARQ worker entrypoint."""

from pathlib import Path

from adapters.llm.openai_provider import OpenAIProvider
from adapters.storage.epub_parser import EpubParser
from adapters.storage.local_ebook_storage import LocalEbookStorage
from core.config import settings
from core.services.chunking import chunk_chapters
from core.services.knowledge_extraction import KnowledgeExtractionService
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory


async def startup(ctx: dict) -> None:
	ctx["parser"] = EpubParser()
	ctx["storage"] = LocalEbookStorage(Path(settings.ebook_storage_path))
	ctx["llm_provider"] = OpenAIProvider()


async def process_ebook(ctx: dict, book_id: str, storage_key: str) -> None:
	parser: EpubParser = ctx["parser"]
	storage: LocalEbookStorage = ctx["storage"]
	llm_provider: OpenAIProvider = ctx["llm_provider"]
	storage_path = str(Path(settings.ebook_storage_path) / storage_key)

	async with session_factory() as session:
		repository = PostgresBookRepository(session)
		knowledge_repo = PostgresKnowledgeRepository(session)
		await repository.mark_processing(book_id)
		try:
			chapters = await parser.parse(storage_path)
		except Exception as error:
			await repository.mark_failed(book_id, str(error))
			return

		chunks = chunk_chapters(chapters)
		try:
			await repository.replace_derived_content(book_id, chapters, chunks)
			chunk_ids = await repository.get_chunk_ids_by_book(book_id)
			chunk_id_map = {idx: cid for cid, idx in chunk_ids}
			chunks_with_ids = [
				(chunk_id_map[c.chunk_index], c) for c in chunks
			]
			extraction = KnowledgeExtractionService(llm_provider, knowledge_repo)
			await extraction.extract_from_chunks(book_id, chunks_with_ids)
			await repository.mark_ready(book_id)
			await storage.delete(storage_key)
		except Exception as error:
			await repository.mark_failed(book_id, str(error))
			if isinstance(error, (ValueError, EOFError)):
				return
			raise


class WorkerSettings:
	functions = [process_ebook]
	on_startup = startup
	max_tries = 3
