"""ARQ worker entrypoint."""

import logging
from pathlib import Path
from typing import ClassVar

from arq.connections import RedisSettings

from adapters.events.redis_book_status import RedisBookStatusPublisher
from adapters.llm.failover_provider import FailoverLLMProvider
from adapters.llm.mock_provider import MockLLMProvider
from adapters.llm.openai_provider import OpenAIProvider
from adapters.queue.arq_graph_queue import ArqGraphGenerationQueue
from adapters.storage.epub_parser import EpubParser
from adapters.storage.local_ebook_storage import LocalEbookStorage
from core.config import settings
from core.domain.status import FAILED, GRAPH_STATUSES, PARTIAL, PROCESSING, READY
from core.ports.book_status_events import BookStatusPublisher
from core.ports.llm_provider import LLMConfigurationError, LLMQuotaExhaustedError
from core.services.chunking import chunk_chapters
from core.services.entity_resolution import EntityResolutionService
from core.services.knowledge_extraction import KnowledgeExtractionService
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory
from rag.adapters.embeddings.gemini import GeminiEmbeddingProvider
from rag.adapters.embeddings.mock import MockEmbeddingProvider
from rag.adapters.persistence.repository import PostgresRagRepository
from rag.adapters.queue.arq_rag_queue import ArqRagIndexQueue
from rag.application.build_index import BuildRagIndexUseCase
from rag.application.embeddings import EmbedKnowledgeService
from rag.clustering.leiden import LeidenCommunityDetector
from rag.clustering.service import CommunityBuilder
from rag.domain.clustering import ClusterParameters
from rag.domain.embeddings import EMBEDDING_DIMENSIONS
from rag.ports.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


def _llm_models() -> list[str]:
	models = [settings.llm_model]
	models.extend(settings.llm_fallback_models.split(","))
	return list(dict.fromkeys(model.strip() for model in models if model.strip()))


def _build_llm_provider() -> FailoverLLMProvider | MockLLMProvider:
	if settings.llm_provider == "mock":
		if not settings.allow_mock_llm:
			raise RuntimeError(
				"LLM_PROVIDER=mock requires ALLOW_MOCK_LLM=true"
			)
		logger.warning(
			"Mock LLM provider enabled; extraction will return empty knowledge"
		)
		return MockLLMProvider()
	return FailoverLLMProvider(
		[OpenAIProvider(model=model) for model in _llm_models()]
	)


def _build_embedding_provider() -> EmbeddingProvider:
	if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
		raise RuntimeError(
			f"EMBEDDING_DIMENSIONS must be {EMBEDDING_DIMENSIONS}"
		)
	if settings.embedding_provider == "mock":
		if not settings.allow_mock_embeddings:
			raise RuntimeError(
				"EMBEDDING_PROVIDER=mock requires ALLOW_MOCK_EMBEDDINGS=true"
			)
		logger.warning("Mock embedding provider enabled; vectors are deterministic")
		return MockEmbeddingProvider()
	return GeminiEmbeddingProvider()


def _cluster_parameters() -> ClusterParameters:
	return ClusterParameters(
		resolution=settings.community_resolution,
		max_levels=settings.community_max_levels,
		min_size=settings.community_min_size,
		seed=settings.community_seed,
		objective="modularity",
		fact_edge_weight=settings.community_fact_edge_weight,
		cooccurrence_edge_weight=settings.community_cooccurrence_edge_weight,
	)


def _build_extraction_service(
	llm_provider: FailoverLLMProvider | MockLLMProvider,
	knowledge_repository: PostgresKnowledgeRepository,
) -> KnowledgeExtractionService:
	return KnowledgeExtractionService(
		llm_provider,
		knowledge_repository,
		concurrency=settings.extraction_concurrency,
		max_attempts=settings.extraction_max_attempts,
		retry_base_seconds=settings.extraction_retry_base_seconds,
		retry_max_seconds=settings.extraction_retry_max_seconds,
		requests_per_minute=settings.extraction_requests_per_minute,
		batch_size=settings.extraction_batch_size,
	)


async def startup(ctx: dict) -> None:
	ctx["parser"] = EpubParser()
	ctx["storage"] = LocalEbookStorage(Path(settings.ebook_storage_path))
	ctx["llm_provider"] = _build_llm_provider()
	ctx["embedding_provider"] = _build_embedding_provider()
	ctx["status_publisher"] = RedisBookStatusPublisher(settings.redis_url)
	ctx["session_factory"] = session_factory
	ctx["book_repository_factory"] = PostgresBookRepository
	ctx["knowledge_repository_factory"] = PostgresKnowledgeRepository
	ctx["rag_repository_factory"] = PostgresRagRepository
	ctx["extraction_service_factory"] = _build_extraction_service
	ctx["graph_queue"] = ArqGraphGenerationQueue(settings.redis_url)
	ctx["rag_queue"] = ArqRagIndexQueue(settings.redis_url)


async def shutdown(ctx: dict) -> None:
	publisher: BookStatusPublisher | None = ctx.get("status_publisher")
	if publisher is not None:
		await publisher.aclose()


async def _publish_status(
	publisher: BookStatusPublisher | None,
	book_id: str,
	status: str,
	error: str | None = None,
) -> None:
	if publisher is None:
		return
	try:
		await publisher.publish(book_id, status, error)
	except Exception:
		logger.exception("Could not publish %s status for book %s", status, book_id)


async def process_ebook(ctx: dict, book_id: str, storage_key: str) -> None:
	parser: EpubParser = ctx["parser"]
	storage: LocalEbookStorage = ctx["storage"]
	llm_provider: FailoverLLMProvider | MockLLMProvider = ctx["llm_provider"]
	publisher: BookStatusPublisher | None = ctx.get("status_publisher")
	storage_path = str(Path(settings.ebook_storage_path) / storage_key)

	async with ctx["session_factory"]() as session:
		repository = ctx["book_repository_factory"](session)
		knowledge_repo = ctx["knowledge_repository_factory"](session)
		await repository.mark_processing(book_id)
		await _publish_status(publisher, book_id, PROCESSING)
		try:
			chapters = await parser.parse(storage_path)
			cover_content = await parser.extract_cover(storage_path)
			if cover_content:
				cover_key = f"{book_id}/cover.jpg"
				cover_path = await storage.save(cover_key, cover_content)
				await repository.set_cover_path(book_id, cover_path)
		except Exception as error:  # noqa: BLE001
			await repository.mark_failed(book_id, str(error))
			await _publish_status(publisher, book_id, FAILED, str(error))
			return

		chunks = chunk_chapters(chapters)
		try:
			await ctx["rag_repository_factory"](session).delete_by_book(book_id)
			await repository.replace_derived_content(book_id, chapters, chunks)
			chunk_ids = await repository.get_chunk_ids_by_book(book_id)
			chunk_id_map = {idx: cid for cid, idx in chunk_ids}
			chunks_with_ids = [
				(chunk_id_map[c.chunk_index], c) for c in chunks
			]
			extraction = ctx["extraction_service_factory"](
				llm_provider, knowledge_repo
			)
			summary = await extraction.extract_from_chunks(book_id, chunks_with_ids)
			logger.info("Book %s extraction summary: %s", book_id, summary)
			if summary.failed:
				error = summary.error or (
					f"{summary.failed} of {summary.total} chunks failed extraction"
				)
				await repository.mark_partial(book_id, error)
				await _publish_status(publisher, book_id, PARTIAL, error)
			else:
				await storage.delete(storage_key)
				await repository.mark_ready(book_id)
				await _publish_status(publisher, book_id, READY)
		except (LLMConfigurationError, LLMQuotaExhaustedError) as error:
			await repository.mark_failed(book_id, str(error))
			await _publish_status(publisher, book_id, FAILED, str(error))
			return
		except Exception as error:
			await repository.mark_failed(book_id, str(error))
			await _publish_status(publisher, book_id, FAILED, str(error))
			if isinstance(error, (ValueError, EOFError)):
				return
			raise

	await _enqueue_graph_generation(ctx, book_id)


async def _enqueue_graph_generation(ctx: dict, book_id: str) -> None:
	try:
		await ctx["graph_queue"].enqueue(book_id)
	except Exception:
		logger.exception("Could not queue initial graph generation for book %s", book_id)


async def generate_graph(ctx: dict, book_id: str) -> None:
	"""Refresh entity identity for a book so graph nodes merge across chunks."""
	llm_provider: FailoverLLMProvider | MockLLMProvider = ctx["llm_provider"]

	async with ctx["session_factory"]() as session:
		book_repository = ctx["book_repository_factory"](session)
		knowledge_repository = ctx["knowledge_repository_factory"](session)

		state = await book_repository.get_state(book_id)
		if state is None:
			logger.warning("Graph generation skipped, book %s does not exist", book_id)
			return
		if state.processing_status not in GRAPH_STATUSES:
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

		if resolution.canonical_by_entity:
			if resolution.changed:
				await knowledge_repository.apply_resolution(
					book_id,
					resolution.canonical_by_entity,
					resolution.method_by_entity,
				)
				revision = await book_repository.bump_graph_revision(book_id)
				logger.info(
					"Book %s graph resolution applied at revision %s",
					book_id,
					revision,
				)
			else:
				logger.info("Entity resolution unchanged for book %s", book_id)
		else:
			logger.info("No entity mentions to resolve for book %s", book_id)

		await _enqueue_rag_build_if_needed(ctx, book_id)


async def _enqueue_rag_build_if_needed(ctx: dict, book_id: str) -> None:
	try:
		async with ctx["session_factory"]() as session:
			repository = ctx["rag_repository_factory"](session)
			graph_revision = await repository.get_graph_revision(book_id)
			if not await repository.needs_build(
				book_id, graph_revision, settings.embedding_model
			):
				return
		await ctx["rag_queue"].enqueue(
			book_id, graph_revision, settings.embedding_model
		)
	except Exception:
		logger.exception("Could not queue RAG index build for book %s", book_id)


async def build_rag_index(ctx: dict, book_id: str) -> None:
	provider: EmbeddingProvider = ctx["embedding_provider"]

	async with ctx["session_factory"]() as session:
		repository = ctx["rag_repository_factory"](session)
		graph_revision = await repository.get_graph_revision(book_id)
		if not await repository.needs_build(book_id, graph_revision, provider.model):
			logger.info("RAG index for book %s is already current", book_id)
			return

		use_case = BuildRagIndexUseCase(
			repository,
			EmbedKnowledgeService(
				provider,
				repository,
				dimensions=settings.embedding_dimensions,
				batch_size=settings.embedding_batch_size,
				max_attempts=settings.embedding_max_attempts,
				retry_base_seconds=settings.embedding_retry_base_seconds,
				retry_max_seconds=settings.embedding_retry_max_seconds,
			),
			CommunityBuilder(
				repository,
				LeidenCommunityDetector(),
				_cluster_parameters(),
			),
			provider.model,
		)
		await use_case.execute(book_id, graph_revision)


class WorkerSettings:
	functions: ClassVar[list] = [process_ebook, generate_graph, build_rag_index]
	on_startup = startup
	on_shutdown = shutdown
	max_tries = 3
	job_timeout = settings.extraction_job_timeout_seconds
	redis_settings = RedisSettings.from_dsn(settings.redis_url)
