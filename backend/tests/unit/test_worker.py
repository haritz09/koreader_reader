import asyncio
from urllib.parse import urlparse

import pytest

import workers.worker as worker_module
from core.config import settings
from core.domain.entities.chapter import Chapter
from core.ports.llm_provider import LLMConfigurationError, LLMQuotaExhaustedError
from core.services.knowledge_extraction import ExtractionSummary


class FakeSessionContext:
	async def __aenter__(self):
		return object()

	async def __aexit__(self, exc_type, exc_value, traceback):
		return False


class FakeRepository:
	def __init__(self, replace_error: Exception | None = None) -> None:
		self.replace_error = replace_error
		self.calls: list[tuple[str, str]] = []

	async def mark_processing(self, book_id: str) -> None:
		self.calls.append(("processing", book_id))

	async def replace_derived_content(self, book_id, chapters, chunks) -> None:
		if self.replace_error is not None:
			raise self.replace_error
		self.calls.append(("replace", book_id))

	async def mark_ready(self, book_id: str) -> None:
		self.calls.append(("ready", book_id))

	async def mark_failed(self, book_id: str, error: str) -> None:
		self.calls.append(("failed", error))

	async def mark_partial(self, book_id: str, error: str) -> None:
		self.calls.append(("partial", book_id))

	async def get_chunk_ids_by_book(self, book_id: str) -> list[tuple[str, int]]:
		return []


class FakeKnowledgeRepository:
	async def insert_batch(self, book_id, result) -> None:
		pass


class FakeRagRepository:
	def __init__(
		self,
		needs_build: bool = False,
		*,
		claim_result: bool = True,
		sources=None,
	) -> None:
		self.needs_build_value = needs_build
		self.claim_result = claim_result
		self.sources = list(sources or [])
		self.revision = 0
		self.deleted: list[str] = []
		self.checked: list[tuple] = []
		self.claims: list[tuple] = []
		self.pending: list[tuple[str, str | None]] = []
		self.failures: list[tuple[str, str]] = []
		self.rows: list = []

	async def delete_by_book(self, book_id: str) -> None:
		self.deleted.append(book_id)

	async def get_graph_revision(self, book_id: str) -> int:
		return self.revision

	async def needs_build(
		self,
		book_id: str,
		graph_revision: int,
		embedding_model: str,
		stale_after_seconds: int,
	) -> bool:
		self.checked.append(
			(book_id, graph_revision, embedding_model, stale_after_seconds)
		)
		return self.needs_build_value

	async def claim_build(
		self,
		book_id: str,
		graph_revision: int,
		embedding_model: str,
		stale_after_seconds: int,
	) -> bool:
		self.claims.append(
			(book_id, graph_revision, embedding_model, stale_after_seconds)
		)
		return self.claim_result

	async def mark_pending(self, book_id: str, error: str | None = None) -> None:
		self.pending.append((book_id, error))

	async def mark_failed(self, book_id: str, error: str) -> None:
		self.failures.append((book_id, error))

	async def get_embedding_sources(self, book_id: str):
		return list(self.sources)

	async def get_existing_hashes(self, book_id: str, model: str):
		return {}

	async def upsert_embeddings(self, book_id, model, rows) -> None:
		self.rows.extend(rows)


class FakeGraphQueue:
	def __init__(self) -> None:
		self.enqueued: list[str] = []

	async def enqueue(self, book_id: str) -> None:
		self.enqueued.append(book_id)


class FakeRagQueue:
	def __init__(self) -> None:
		self.enqueued: list[tuple[str, int, str]] = []
		self.deferred: list[tuple[str, int, str, float]] = []

	async def enqueue(
		self,
		book_id: str,
		graph_revision: int,
		embedding_model: str,
		*,
		defer_by_seconds: float | None = None,
	) -> None:
		if defer_by_seconds is None:
			self.enqueued.append((book_id, graph_revision, embedding_model))
		else:
			self.deferred.append(
				(book_id, graph_revision, embedding_model, defer_by_seconds)
			)


class FakeParser:
	def __init__(self, chapters, error: Exception | None = None) -> None:
		self.chapters = chapters
		self.error = error

	async def parse(self, storage_path: str):
		if self.error is not None:
			raise self.error
		return self.chapters

	async def extract_cover(self, storage_path: str):
		return None


class FakeStorage:
	def __init__(self) -> None:
		self.deleted: list[str] = []

	async def delete(self, storage_key):
		self.deleted.append(storage_key)


class FakeLLM:
	async def extract_knowledge_batch(self, chunks):
		from core.domain.entities.knowledge import KnowledgeExtractionResult

		return {
			chunk_id: KnowledgeExtractionResult(
				entities=[], facts=[], events=[], locations=[]
			)
			for chunk_id, _ in chunks
		}


class FakeEmbeddings:
	model = settings.embedding_model
	dimensions = settings.embedding_dimensions
	max_batch_size = 100


class QuotaEmbeddings(FakeEmbeddings):
	async def embed_documents(self, texts):
		from rag.domain.errors import EmbeddingQuotaExhaustedError

		raise EmbeddingQuotaExhaustedError("daily quota")


class FakeExtraction:
	def __init__(self, error: Exception | None = None) -> None:
		self.error = error

	async def extract_from_chunks(self, book_id, chunks) -> ExtractionSummary:
		if self.error is not None:
			raise self.error
		return ExtractionSummary(0, 0, 0, 0, 0, 0, 0)


def make_ctx(
	repository: FakeRepository,
	*,
	rag_repository: FakeRagRepository | None = None,
	chapters: list[Chapter] | None = None,
	parser_error: Exception | None = None,
	extraction: FakeExtraction | None = None,
	graph_queue: FakeGraphQueue | None = None,
	rag_queue: FakeRagQueue | None = None,
) -> dict:
	if chapters is None:
		chapters = [Chapter("chapter", "Chapter", "one two three", 0)]
	rag_repository = rag_repository or FakeRagRepository()
	extraction = extraction or FakeExtraction()
	storage = FakeStorage()
	return {
		"parser": FakeParser(chapters, parser_error),
		"storage": storage,
		"llm_provider": FakeLLM(),
		"embedding_provider": FakeEmbeddings(),
		"status_publisher": None,
		"session_factory": lambda: FakeSessionContext(),
		"book_repository_factory": lambda session: repository,
		"knowledge_repository_factory": lambda session: FakeKnowledgeRepository(),
		"rag_repository_factory": lambda session: rag_repository,
		"extraction_service_factory": lambda provider, repo: extraction,
		"graph_queue": graph_queue or FakeGraphQueue(),
		"rag_queue": rag_queue or FakeRagQueue(),
		"_storage": storage,
	}


def test_worker_marks_corrupt_epub_failed_without_retry() -> None:
	repository = FakeRepository()
	ctx = make_ctx(repository, parser_error=ValueError("corrupt EPUB"))

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert repository.calls == [
		("processing", "book-123"),
		("failed", "corrupt EPUB"),
	]


def test_worker_reraises_processing_failure_for_arq_retry() -> None:
	repository = FakeRepository(RuntimeError("database unavailable"))
	ctx = make_ctx(repository)

	with pytest.raises(RuntimeError, match="database unavailable"):
		asyncio.run(
			worker_module.process_ebook(ctx, "book-123", "books/book-123.epub")
		)

	assert repository.calls == [
		("processing", "book-123"),
		("failed", "database unavailable"),
	]


def test_worker_marks_configuration_errors_failed_without_retry() -> None:
	repository = FakeRepository()
	ctx = make_ctx(
		repository,
		chapters=[],
		extraction=FakeExtraction(LLMConfigurationError("invalid key")),
	)

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert repository.calls == [
		("processing", "book-123"),
		("replace", "book-123"),
		("failed", "invalid key"),
	]


def test_worker_allows_three_attempts_for_retryable_jobs() -> None:
	assert worker_module.WorkerSettings.max_tries == 3


def test_worker_marks_quota_exhaustion_failed_without_retry() -> None:
	repository = FakeRepository()
	ctx = make_ctx(
		repository,
		chapters=[],
		extraction=FakeExtraction(
			LLMQuotaExhaustedError("All configured models exhausted", 3600)
		),
	)

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert repository.calls == [
		("processing", "book-123"),
		("replace", "book-123"),
		("failed", "All configured models exhausted"),
	]


def test_worker_marks_incomplete_extraction_partial_and_keeps_source() -> None:
	repository = FakeRepository()
	ctx = make_ctx(repository, chapters=[])

	class PartialExtraction(FakeExtraction):
		async def extract_from_chunks(self, book_id, chunks) -> ExtractionSummary:
			return ExtractionSummary(2, 1, 1, 0, 0, 0, 0)

	ctx["extraction_service_factory"] = lambda provider, repo: PartialExtraction()

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert repository.calls == [
		("processing", "book-123"),
		("replace", "book-123"),
		("partial", "book-123"),
	]
	assert ctx["_storage"].deleted == []


def test_worker_clears_the_previous_rag_index_before_replacing_content() -> None:
	repository = FakeRepository()
	rag_repository = FakeRagRepository()
	ctx = make_ctx(repository, rag_repository=rag_repository, chapters=[])

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert rag_repository.deleted == ["book-123"]
	assert repository.calls[-1] == ("ready", "book-123")


def test_worker_uses_the_configured_extraction_timeout() -> None:
	assert worker_module.WorkerSettings.job_timeout == settings.extraction_job_timeout_seconds


def test_worker_connects_to_the_configured_redis() -> None:
	redis_settings = worker_module.WorkerSettings.redis_settings

	assert redis_settings.host == urlparse(settings.redis_url).hostname
	assert redis_settings.port == urlparse(settings.redis_url).port


def test_worker_settings_registers_the_graph_generation_job() -> None:
	assert worker_module.generate_graph in worker_module.WorkerSettings.functions


def test_worker_settings_registers_the_rag_index_job() -> None:
	assert worker_module.build_rag_index in worker_module.WorkerSettings.functions


class FakeGraphBookRepository:
	def __init__(
		self,
		state=None,
		candidates=None,
		stored=None,
	) -> None:
		self.state = state
		self.candidates = candidates or []
		self.stored = dict(stored or {})
		self.applied: list[dict[str, str]] = []
		self.revision_bumps: list[str] = []

	async def get_state(self, book_id: str):
		return self.state

	async def get_entity_candidates(self, book_id: str):
		return list(self.candidates)

	async def get_resolution(self, book_id: str):
		return dict(self.stored)

	async def apply_resolution(
		self, book_id: str, canonical_by_entity, method_by_entity
	) -> None:
		self.applied.append(dict(canonical_by_entity))

	async def bump_graph_revision(self, book_id: str) -> int:
		self.revision_bumps.append(book_id)
		return 1


class ExplodingKnowledgeRepository:
	async def get_entity_candidates(self, book_id: str):
		raise RuntimeError("database unavailable")


def candidate(entity_id: str, name: str, position: float = 0.0):
	from core.domain.entities.graph import EntityCandidate

	return EntityCandidate(
		entity_id=entity_id,
		name=name,
		entity_type="character",
		reading_position=position,
	)


def graph_state(processing_status: str = "ready"):
	from core.domain.entities.graph import BookState

	return BookState(
		book_id="book-123",
		processing_status=processing_status,
	)


def graph_ctx(
	repository,
	rag_repository: FakeRagRepository | None = None,
	rag_queue: FakeRagQueue | None = None,
	knowledge_repository=None,
) -> dict:
	return {
		"llm_provider": object(),
		"session_factory": lambda: FakeSessionContext(),
		"book_repository_factory": lambda session: repository,
		"knowledge_repository_factory": lambda session: (
			knowledge_repository or repository
		),
		"rag_repository_factory": lambda session: (
			rag_repository or FakeRagRepository()
		),
		"rag_queue": rag_queue or FakeRagQueue(),
	}


def run_graph_job(
	repository,
	rag_repository: FakeRagRepository | None = None,
	rag_queue: FakeRagQueue | None = None,
) -> None:
	ctx = graph_ctx(repository, rag_repository, rag_queue)
	asyncio.run(worker_module.generate_graph(ctx, "book-123"))


def test_graph_job_applies_a_new_resolution_and_bumps_the_revision() -> None:
	repository = FakeGraphBookRepository(
		state=graph_state(),
		candidates=[candidate("e1", "Alice", 0.1), candidate("e2", "Alice", 0.7)],
	)

	run_graph_job(repository)

	assert repository.applied == [{"e1": "e1", "e2": "e1"}]
	assert repository.revision_bumps == ["book-123"]


def test_graph_job_queues_a_rag_build_when_the_index_is_stale() -> None:
	rag_repository = FakeRagRepository(needs_build=True)
	rag_repository.revision = 7
	rag_queue = FakeRagQueue()
	repository = FakeGraphBookRepository(state=graph_state())

	run_graph_job(repository, rag_repository, rag_queue)

	assert rag_queue.enqueued == [("book-123", 7, settings.embedding_model)]


def test_graph_job_skips_the_rag_queue_when_the_index_is_current() -> None:
	rag_queue = FakeRagQueue()
	repository = FakeGraphBookRepository(state=graph_state())

	run_graph_job(repository, FakeRagRepository(needs_build=False), rag_queue)

	assert rag_queue.enqueued == []


def test_graph_job_skips_the_revision_when_the_resolution_is_unchanged() -> None:
	repository = FakeGraphBookRepository(
		state=graph_state(),
		candidates=[candidate("e1", "Alice", 0.1)],
		stored={"e1": ("e1", "deterministic")},
	)

	run_graph_job(repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_skips_a_book_that_is_not_ready() -> None:
	repository = FakeGraphBookRepository(
		state=graph_state(processing_status="processing"),
		candidates=[candidate("e1", "Alice", 0.1)],
	)

	run_graph_job(repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_skips_an_unknown_book() -> None:
	repository = FakeGraphBookRepository(state=None, candidates=[candidate("e1", "Alice")])

	run_graph_job(repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_skips_a_book_without_mentions() -> None:
	repository = FakeGraphBookRepository(state=graph_state(), candidates=[])

	run_graph_job(repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_swallows_a_resolution_failure_without_raising() -> None:
	book_repository = FakeGraphBookRepository(state=graph_state())
	ctx = graph_ctx(book_repository, knowledge_repository=ExplodingKnowledgeRepository())

	asyncio.run(worker_module.generate_graph(ctx, "book-123"))

	assert book_repository.applied == []
	assert book_repository.revision_bumps == []


def embedding_source():
	from rag.domain.embeddings import EmbeddingSource, EmbeddingSourceType

	return EmbeddingSource(
		source_type=EmbeddingSourceType.CHUNK,
		source_id="chunk-1",
		chunk_id="chunk-1",
		reading_position=0.1,
		text="some text",
	)


def test_build_job_skips_when_another_job_holds_the_claim() -> None:
	rag_repository = FakeRagRepository(claim_result=False)
	ctx = make_ctx(FakeRepository(), rag_repository=rag_repository)

	asyncio.run(worker_module.build_rag_index(ctx, "book-123"))

	assert rag_repository.claims == [
		(
			"book-123",
			0,
			settings.embedding_model,
			settings.rag_build_stale_seconds,
		)
	]
	assert rag_repository.rows == []


def test_build_job_defers_after_daily_quota_exhaustion() -> None:
	rag_repository = FakeRagRepository(sources=[embedding_source()])
	rag_queue = FakeRagQueue()
	ctx = make_ctx(
		FakeRepository(),
		rag_repository=rag_repository,
		rag_queue=rag_queue,
	)
	ctx["embedding_provider"] = QuotaEmbeddings()

	asyncio.run(worker_module.build_rag_index(ctx, "book-123"))

	assert rag_repository.pending == [("book-123", "daily quota")]
	assert rag_repository.rows == []
	assert rag_queue.enqueued == []
	assert rag_queue.deferred == [
		(
			"book-123",
			0,
			settings.embedding_model,
			settings.embedding_quota_defer_seconds,
		)
	]
