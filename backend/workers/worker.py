"""ARQ worker entrypoint."""

import logging
from pathlib import Path
from typing import ClassVar

from arq.connections import RedisSettings

from adapters.llm.openai_provider import OpenAIProvider
from adapters.queue.arq_graph_queue import ArqGraphGenerationQueue
from adapters.storage.epub_parser import EpubParser
from adapters.storage.local_ebook_storage import LocalEbookStorage
from core.config import settings
from core.services.chunking import chunk_chapters
from core.services.entity_resolution import EntityResolutionService
from core.services.knowledge_extraction import KnowledgeExtractionService
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory

logger = logging.getLogger(__name__)


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
			cover_content = await parser.extract_cover(storage_path)
			if cover_content:
				cover_key = f"{book_id}/cover.jpg"
				cover_path = await storage.save(cover_key, cover_content)
				await repository.set_cover_path(book_id, cover_path)
		except Exception as error:  # noqa: BLE001 - any parse failure must mark the book failed
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

	await _enqueue_graph_generation(book_id)


async def _enqueue_graph_generation(book_id: str) -> None:
	"""Queue a first resolution pass once extraction has finished.

	Progress sync also queues this, but only when the reader moves forward, so a
	book that is uploaded and opened at position zero would otherwise show
	unmerged nodes until the first advance.
	"""
	try:
		await ArqGraphGenerationQueue(settings.redis_url).enqueue(book_id)
	except Exception:
		logger.exception("Could not queue initial graph generation for book %s", book_id)


async def generate_graph(ctx: dict, book_id: str) -> None:
	"""Refresh entity identity for a book so graph nodes merge across chunks.

	This is an optimization, not a gate. The graph read filters by the stored
	reading position on every request and derives node labels from visible
	mentions only, so a failed or skipped run costs freshness and never leaks a
	future mention.
	"""
	llm_provider: OpenAIProvider = ctx["llm_provider"]

	async with session_factory() as session:
		book_repository = PostgresBookRepository(session)
		knowledge_repository = PostgresKnowledgeRepository(session)

		state = await book_repository.get_graph_state(book_id)
		if state is None:
			logger.warning("Graph generation skipped, book %s does not exist", book_id)
			return
		if state.processing_status != "ready":
			logger.info(
				"Graph generation skipped for book %s in status %s",
				book_id,
				state.processing_status,
			)
			return

		try:
			resolution = await EntityResolutionService(
				knowledge_repository, llm_provider
			).resolve(book_id)
		except Exception:
			logger.exception("Entity resolution failed for book %s", book_id)
			return

		if not resolution.canonical_by_entity:
			logger.info("No entity mentions to resolve for book %s", book_id)
			return
		if not resolution.changed:
			logger.info("Entity resolution unchanged for book %s", book_id)
			return

		await knowledge_repository.apply_resolution(
			book_id,
			resolution.canonical_by_entity,
			resolution.method_by_entity,
		)
		revision = await book_repository.bump_graph_revision(book_id)
		logger.info("Book %s graph resolution applied at revision %s", book_id, revision)


class WorkerSettings:
	functions: ClassVar[list] = [process_ebook, generate_graph]
	on_startup = startup
	max_tries = 3
	redis_settings = RedisSettings.from_dsn(settings.redis_url)
