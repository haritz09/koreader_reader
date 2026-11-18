"""ARQ worker entrypoint."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.events.redis_book_status import RedisBookStatusPublisher
from adapters.llm.failover_provider import FailoverLLMProvider
from adapters.llm.mock_provider import MockLLMProvider
from adapters.provider_factory import build_embedding_provider, build_llm_provider
from adapters.queue.arq_graph_queue import ArqGraphGenerationQueue
from adapters.storage.epub_parser import EpubParser
from adapters.storage.local_ebook_storage import LocalEbookStorage
from core.config import settings
from core.domain.entities.chapter import Chapter
from core.domain.entities.chunk import Chunk
from core.domain.errors import KnowledgeExtractionError
from core.domain.status import FAILED, GRAPH_STATUSES, PARTIAL, PROCESSING, READY
from core.ports.book_status_events import BookStatusPublisher
from core.ports.llm_provider import LLMConfigurationError, LLMQuotaExhaustedError
from core.services.chunking import chunk_chapters
from core.services.entity_resolution import EntityResolutionService
from core.services.knowledge_extraction import ExtractionSummary, KnowledgeExtractionService
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory
from rag.adapters.persistence.repository import PostgresRagRepository
from rag.adapters.queue.arq_rag_queue import ArqRagIndexQueue
from rag.application.build_index import BuildRagIndexUseCase
from rag.application.embeddings import EmbedKnowledgeService
from rag.clustering.leiden import LeidenCommunityDetector
from rag.clustering.service import CommunityBuilder
from rag.domain.clustering import ClusterParameters
from rag.domain.errors import RagBuildDeferred
from rag.ports.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


def _cluster_parameters() -> ClusterParameters:
	return ClusterParameters(
		resolution=settings.community_resolution,
		max_levels=settings.community_max_levels,
		min_size=settings.community_min_size,
		min_members=settings.community_min_members,
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
	ctx["llm_provider"] = build_llm_provider()
	ctx["embedding_provider"] = build_embedding_provider()
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


@dataclass(frozen=True)
class _Source:
	"""Chunk work left for one processing run."""

	total_chunks: int
	extracted_chunks: int
	pending_chunks: list[tuple[str, Chunk]]


@dataclass(frozen=True)
class _ExtractionOutcome:
	summary: ExtractionSummary | None
	error: str | None


async def _publish_status(
	publisher: BookStatusPublisher | None,
	book_id: str,
	status: str,
	error: str | None = None,
	*,
	chunks_total: int | None = None,
	chunks_extracted: int | None = None,
) -> None:
	if publisher is None:
		return
	try:
		await publisher.publish(
			book_id,
			status,
			error,
			chunks_total=chunks_total,
			chunks_extracted=chunks_extracted,
		)
	except Exception:
		logger.exception("Could not publish %s status for book %s", status, book_id)


async def _record_failure(
	book_repository: PostgresBookRepository,
	publisher: BookStatusPublisher | None,
	book_id: str,
	error: BaseException | str,
	*,
	chunks_total: int | None = None,
	chunks_extracted: int | None = None,
) -> None:
	message = str(error)
	await book_repository.mark_failed(book_id, message)
	await _publish_status(
		publisher,
		book_id,
		FAILED,
		message,
		chunks_total=chunks_total,
		chunks_extracted=chunks_extracted,
	)


def _progress_reporter(
	publisher: BookStatusPublisher | None,
	book_id: str,
	source: _Source,
) -> Callable[[int], Awaitable[None]]:
	async def report(extracted_in_run: int) -> None:
		await _publish_status(
			publisher,
			book_id,
			PROCESSING,
			chunks_total=source.total_chunks,
			chunks_extracted=source.extracted_chunks + extracted_in_run,
		)

	return report


async def _save_cover(
	ctx: dict,
	book_repository: PostgresBookRepository,
	book_id: str,
	storage_path: str,
) -> None:
	cover = await ctx["parser"].extract_cover(storage_path)
	if not cover:
		return
	cover_path = await ctx["storage"].save(f"{book_id}/cover.jpg", cover)
	await book_repository.set_cover_path(book_id, cover_path)


async def _prepare_source(
	ctx: dict,
	session: AsyncSession,
	book_repository: PostgresBookRepository,
	book_id: str,
	storage_path: str,
	publisher: BookStatusPublisher | None,
) -> _Source | None:
	total = await book_repository.count_chunks(book_id)
	is_new = total == 0
	chapters: list[Chapter] = []
	chunks: list[Chunk] = []

	if is_new:
		try:
			chapters = await ctx["parser"].parse(storage_path)
			await _save_cover(ctx, book_repository, book_id, storage_path)
		except Exception as error:  # noqa: BLE001
			await _record_failure(book_repository, publisher, book_id, error)
			return None
		chunks = chunk_chapters(chapters)
		total = len(chunks)

	try:
		await ctx["rag_repository_factory"](session).delete_by_book(book_id)
		if is_new:
			await book_repository.replace_derived_content(book_id, chapters, chunks)
		pending = await book_repository.get_pending_chunks(book_id)
	except Exception as error:
		await _record_failure(book_repository, publisher, book_id, error)
		if isinstance(error, (ValueError, EOFError)):
			return None
		raise

	return _Source(total, total - len(pending), pending)


async def _run_extraction(
	ctx: dict,
	session: AsyncSession,
	book_id: str,
	source: _Source,
	on_progress: Callable[[int], Awaitable[None]],
) -> _ExtractionOutcome:
	if not source.pending_chunks:
		return _ExtractionOutcome(None, None)

	extraction = ctx["extraction_service_factory"](
		ctx["llm_provider"], ctx["knowledge_repository_factory"](session)
	)
	try:
		summary = await extraction.extract_from_chunks(
			book_id,
			source.pending_chunks,
			on_progress=on_progress,
		)
	except (LLMQuotaExhaustedError, KnowledgeExtractionError) as error:
		return _ExtractionOutcome(None, str(error))

	logger.info("Book %s extraction summary: %s", book_id, summary)
	error = None
	if summary.failed:
		error = summary.error or (
			f"{summary.failed} of {source.total_chunks} chunks failed extraction"
		)
	return _ExtractionOutcome(summary, error)


async def _finish_book(
	ctx: dict,
	book_repository: PostgresBookRepository,
	publisher: BookStatusPublisher | None,
	book_id: str,
	storage_key: str,
	source: _Source,
	outcome: _ExtractionOutcome,
) -> None:
	extracted = source.extracted_chunks + (
		outcome.summary.succeeded if outcome.summary is not None else 0
	)
	counts = {"chunks_total": source.total_chunks, "chunks_extracted": extracted}

	if (
		outcome.error
		and outcome.summary is None
		and source.total_chunks == len(source.pending_chunks)
	):
		await _record_failure(book_repository, publisher, book_id, outcome.error, **counts)
		return

	if outcome.error:
		await book_repository.mark_partial(book_id, outcome.error)
		await _publish_status(publisher, book_id, PARTIAL, outcome.error, **counts)
		return

	await ctx["storage"].delete(storage_key)
	await book_repository.mark_ready(book_id)
	await _publish_status(publisher, book_id, READY, **counts)


async def process_ebook(ctx: dict, book_id: str, storage_key: str) -> None:
	publisher: BookStatusPublisher | None = ctx.get("status_publisher")
	storage_path = str(Path(settings.ebook_storage_path) / storage_key)

	async with ctx["session_factory"]() as session:
		book_repository = ctx["book_repository_factory"](session)
		await book_repository.mark_processing(book_id)
		await _publish_status(publisher, book_id, PROCESSING)

		source = await _prepare_source(
			ctx, session, book_repository, book_id, storage_path, publisher
		)
		if source is None:
			return

		report_progress = _progress_reporter(publisher, book_id, source)
		await report_progress(0)

		try:
			outcome = await _run_extraction(ctx, session, book_id, source, report_progress)
		except LLMConfigurationError as error:
			await _record_failure(book_repository, publisher, book_id, error)
			return
		except Exception as error:
			await _record_failure(book_repository, publisher, book_id, error)
			if isinstance(error, (ValueError, EOFError)):
				return
			raise

		await _finish_book(
			ctx, book_repository, publisher, book_id, storage_key, source, outcome
		)

	await _enqueue_graph_generation(ctx, book_id)


async def _enqueue_graph_generation(ctx: dict, book_id: str) -> None:
	try:
		await ctx["graph_queue"].enqueue(book_id)
	except Exception:
		logger.exception("Could not queue initial graph generation for book %s", book_id)


async def _book_is_graph_ready(
	book_repository: PostgresBookRepository,
	book_id: str,
) -> bool:
	state = await book_repository.get_state(book_id)
	if state is None:
		logger.warning("Graph generation skipped, book %s does not exist", book_id)
		return False
	if state.processing_status not in GRAPH_STATUSES:
		logger.info(
			"Graph generation skipped for book %s in status %s",
			book_id,
			state.processing_status,
		)
		return False
	return True


async def _resolve_entities(
	book_repository: PostgresBookRepository,
	knowledge_repository: PostgresKnowledgeRepository,
	llm_provider: FailoverLLMProvider | MockLLMProvider,
	book_id: str,
) -> bool:
	try:
		resolution = await EntityResolutionService(
			knowledge_repository, llm_provider
		).resolve(book_id)
	except Exception:
		logger.exception("Entity resolution failed for book %s", book_id)
		return False

	if not resolution.canonical_by_entity:
		logger.info("No entity mentions to resolve for book %s", book_id)
		return True
	if not resolution.changed:
		logger.info("Entity resolution unchanged for book %s", book_id)
		return True

	await knowledge_repository.apply_resolution(
		book_id,
		resolution.canonical_by_entity,
		resolution.method_by_entity,
	)
	revision = await book_repository.bump_graph_revision(book_id)
	logger.info("Book %s graph resolution applied at revision %s", book_id, revision)
	return True


async def generate_graph(ctx: dict, book_id: str) -> None:
	"""Refresh entity identity for a book so graph nodes merge across chunks."""
	async with ctx["session_factory"]() as session:
		book_repository = ctx["book_repository_factory"](session)
		if not await _book_is_graph_ready(book_repository, book_id):
			return
		knowledge_repository = ctx["knowledge_repository_factory"](session)
		resolved = await _resolve_entities(
			book_repository,
			knowledge_repository,
			ctx["llm_provider"],
			book_id,
		)

	if resolved:
		await _enqueue_rag_build_if_needed(ctx, book_id)


async def _enqueue_rag_build_if_needed(ctx: dict, book_id: str) -> None:
	try:
		async with ctx["session_factory"]() as session:
			repository = ctx["rag_repository_factory"](session)
			graph_revision = await repository.get_graph_revision(book_id)
			if not await repository.needs_build(
				book_id,
				graph_revision,
				settings.embedding_model,
				settings.rag_build_stale_seconds,
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
			stale_after_seconds=settings.rag_build_stale_seconds,
		)
		try:
			await use_case.execute(book_id, graph_revision)
		except RagBuildDeferred as deferred:
			await ctx["rag_queue"].enqueue(
				book_id,
				graph_revision,
				provider.model,
				defer_by_seconds=max(
					deferred.retry_after or 0,
					settings.embedding_quota_defer_seconds,
				),
			)


class WorkerSettings:
	functions: ClassVar[list] = [process_ebook, generate_graph, build_rag_index]
	on_startup = startup
	on_shutdown = shutdown
	max_tries = 3
	job_timeout = settings.extraction_job_timeout_seconds
	redis_settings = RedisSettings.from_dsn(settings.redis_url)
