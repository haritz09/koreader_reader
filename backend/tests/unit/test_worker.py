import asyncio

import pytest

import workers.worker as worker_module
from core.config import settings
from core.domain.entities.chapter import Chapter
from core.domain.entities.chunk import Chunk
from core.ports.llm_provider import LLMConfigurationError, LLMQuotaExhaustedError
from core.services.knowledge_extraction import ExtractionSummary


class FakeSessionContext:
	async def __aenter__(self):
		return object()

	async def __aexit__(self, exc_type, exc_value, traceback):
		return False


class FakeRepository:
	def __init__(
		self,
		replace_error: Exception | None = None,
		*,
		chunk_count: int = 0,
		pending: list[tuple[str, Chunk]] | None = None,
	) -> None:
		self.replace_error = replace_error
		self.chunk_count = chunk_count
		self.pending = list(pending or [])
		self.calls: list[tuple[str, str]] = []

	async def mark_processing(self, book_id: str) -> None:
		self.calls.append(("processing", book_id))

	async def replace_derived_content(self, book_id, chapters, chunks) -> None:
		if self.replace_error is not None:
			raise self.replace_error
		self.calls.append(("replace", book_id))
		self.chunk_count = len(chunks)
		self.pending = [
			(f"chunk-{index}", chunk) for index, chunk in enumerate(chunks)
		]

	async def mark_ready(self, book_id: str) -> None:
		self.calls.append(("ready", book_id))

	async def mark_failed(self, book_id: str, error: str) -> None:
		self.calls.append(("failed", error))

	async def mark_partial(self, book_id: str, error: str) -> None:
		self.calls.append(("partial", book_id))

	async def count_chunks(self, book_id: str) -> int:
		return self.chunk_count

	async def get_pending_chunks(self, book_id: str) -> list[tuple[str, Chunk]]:
		return list(self.pending)


class FakeKnowledgeRepository:
	async def insert_batch(self, book_id, chunk_id, result) -> None:
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


class FakePublisher:
	def __init__(self) -> None:
		self.calls: list[tuple[str, str | None, int | None, int | None]] = []

	async def publish(
		self,
		book_id: str,
		status: str,
		error: str | None = None,
		*,
		chunks_total: int | None = None,
		chunks_extracted: int | None = None,
	) -> None:
		self.calls.append((status, error, chunks_total, chunks_extracted))


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
		self.parsed: list[str] = []

	async def parse(self, storage_path: str):
		self.parsed.append(storage_path)
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
	def __init__(self, retry_after: float | None = None) -> None:
		self.retry_after = retry_after

	async def embed_documents(self, texts):
		from rag.domain.errors import EmbeddingQuotaExhaustedError

		raise EmbeddingQuotaExhaustedError("daily quota", self.retry_after)


class FakeExtraction:
	def __init__(self, error: Exception | None = None) -> None:
		self.error = error
		self.received: list[list] = []

	async def extract_from_chunks(
		self, book_id, chunks, on_progress=None
	) -> ExtractionSummary:
		self.received.append(list(chunks))
		if self.error is not None:
			raise self.error
		if on_progress is not None:
			await on_progress(len(chunks))
		return ExtractionSummary(len(chunks), len(chunks), 0, 0, 0, 0, 0)


def make_ctx(
	repository: FakeRepository,
	*,
	rag_repository: FakeRagRepository | None = None,
	chapters: list[Chapter] | None = None,
	parser_error: Exception | None = None,
	extraction: FakeExtraction | None = None,
	graph_queue: FakeGraphQueue | None = None,
	rag_queue: FakeRagQueue | None = None,
	publisher: FakePublisher | None = None,
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
		"status_publisher": publisher,
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


@pytest.mark.parametrize(
	"error",
	[
		LLMConfigurationError("invalid key"),
		LLMQuotaExhaustedError("All configured models exhausted", 3600),
	],
	ids=["configuration", "quota"],
)
def test_worker_marks_unretryable_llm_failures_failed(error) -> None:
	repository = FakeRepository()
	ctx = make_ctx(
		repository,
		extraction=FakeExtraction(error),
	)

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert repository.calls == [
		("processing", "book-123"),
		("replace", "book-123"),
		("failed", str(error)),
	]


def test_worker_marks_incomplete_extraction_partial_and_keeps_source() -> None:
	repository = FakeRepository()
	ctx = make_ctx(repository)

	class PartialExtraction(FakeExtraction):
		async def extract_from_chunks(
			self, book_id, chunks, on_progress=None
		) -> ExtractionSummary:
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


def test_worker_reports_extraction_progress_against_the_whole_book() -> None:
	chunk = Chunk(
		chapter_id="chapter",
		chunk_index=4,
		text="pending text",
		start_pctg=0.5,
		end_pctg=0.6,
	)
	repository = FakeRepository(chunk_count=5, pending=[("chunk-4", chunk)])
	publisher = FakePublisher()
	ctx = make_ctx(repository, publisher=publisher)

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert publisher.calls == [
		("processing", None, None, None),
		("processing", None, 5, 4),
		("processing", None, 5, 5),
		("ready", None, 5, 5),
	]


def test_worker_resumes_with_only_pending_chunks_without_parsing_again() -> None:
	chunk = Chunk(
		chapter_id="chapter",
		chunk_index=4,
		text="pending text",
		start_pctg=0.5,
		end_pctg=0.6,
	)
	repository = FakeRepository(chunk_count=5, pending=[("chunk-4", chunk)])
	extraction = FakeExtraction()
	ctx = make_ctx(repository, extraction=extraction)

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert ctx["parser"].parsed == []
	assert ("replace", "book-123") not in repository.calls
	assert extraction.received == [[("chunk-4", chunk)]]
	assert repository.calls == [
		("processing", "book-123"),
		("ready", "book-123"),
	]


def test_worker_keeps_previous_chunks_partial_when_resume_extraction_fails() -> None:
	chunk = Chunk(
		chapter_id="chapter",
		chunk_index=4,
		text="pending text",
		start_pctg=0.5,
		end_pctg=0.6,
	)
	repository = FakeRepository(chunk_count=5, pending=[("chunk-4", chunk)])
	ctx = make_ctx(
		repository,
		extraction=FakeExtraction(LLMQuotaExhaustedError("quota exhausted", 3600)),
	)

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert repository.calls[-1] == ("partial", "book-123")
	assert ctx["_storage"].deleted == []


def test_worker_settings_registers_every_job() -> None:
	assert worker_module.WorkerSettings.functions == [
		worker_module.process_ebook,
		worker_module.generate_graph,
		worker_module.build_rag_index,
	]


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


@pytest.mark.parametrize(
	"needs_build",
	[True, False],
	ids=["stale", "current"],
)
def test_graph_job_queues_a_rag_build_only_when_the_index_is_stale(
	needs_build,
) -> None:
	rag_repository = FakeRagRepository(needs_build=needs_build)
	rag_repository.revision = 7
	rag_queue = FakeRagQueue()
	repository = FakeGraphBookRepository(state=graph_state())

	run_graph_job(repository, rag_repository, rag_queue)

	assert rag_repository.checked == [
		("book-123", 7, settings.embedding_model, settings.rag_build_stale_seconds)
	]
	expected = (
		[("book-123", 7, settings.embedding_model)] if needs_build else []
	)
	assert rag_queue.enqueued == expected
	assert rag_queue.deferred == []


def test_graph_job_skips_the_revision_when_the_resolution_is_unchanged() -> None:
	repository = FakeGraphBookRepository(
		state=graph_state(),
		candidates=[candidate("e1", "Alice", 0.1)],
		stored={"e1": ("e1", "deterministic")},
	)

	run_graph_job(repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


@pytest.mark.parametrize(
	"repository",
	[
		FakeGraphBookRepository(
			state=None, candidates=[candidate("e1", "Alice")]
		),
		FakeGraphBookRepository(
			state=graph_state(processing_status="processing"),
			candidates=[candidate("e1", "Alice", 0.1)],
		),
		FakeGraphBookRepository(state=graph_state(), candidates=[]),
	],
	ids=["unknown-book", "not-ready", "no-mentions"],
)
def test_graph_job_skips_books_that_cannot_be_resolved(repository) -> None:
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
	rag_queue = FakeRagQueue()
	ctx = make_ctx(
		FakeRepository(),
		rag_repository=rag_repository,
		rag_queue=rag_queue,
	)

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
	assert rag_repository.pending == []
	assert rag_repository.failures == []
	assert rag_queue.enqueued == []
	assert rag_queue.deferred == []


@pytest.mark.parametrize(
	("retry_after", "expected_defer"),
	[
		(None, settings.embedding_quota_defer_seconds),
		(999_999.0, 999_999.0),
	],
	ids=["adapter-default", "adapter-delay"],
)
def test_build_job_defers_after_daily_quota_exhaustion(
	retry_after, expected_defer
) -> None:
	rag_repository = FakeRagRepository(sources=[embedding_source()])
	rag_queue = FakeRagQueue()
	ctx = make_ctx(
		FakeRepository(),
		rag_repository=rag_repository,
		rag_queue=rag_queue,
	)
	ctx["embedding_provider"] = QuotaEmbeddings(retry_after)

	asyncio.run(worker_module.build_rag_index(ctx, "book-123"))

	assert rag_repository.claims == [
		(
			"book-123",
			0,
			settings.embedding_model,
			settings.rag_build_stale_seconds,
		)
	]
	assert rag_repository.pending == [("book-123", "daily quota")]
	assert rag_repository.failures == []
	assert rag_repository.rows == []
	assert rag_queue.enqueued == []
	assert rag_queue.deferred == [
		(
			"book-123",
			0,
			settings.embedding_model,
			expected_defer,
		)
	]
