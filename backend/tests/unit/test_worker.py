import asyncio
from urllib.parse import urlparse

import pytest

import workers.worker as worker_module
from core.config import settings


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

	async def get_chunk_ids_by_book(self, book_id: str) -> list[tuple[str, int]]:
		return []


class FakeKnowledgeRepository:
	async def insert_batch(self, book_id, result) -> None:
		pass


def make_ctx(
	repository: FakeRepository,
	parser_error=None,
) -> dict:
	class FakeParser:
		async def parse(self, storage_path: str):
			if parser_error is not None:
				raise parser_error
			return ["chapter"]

		async def extract_cover(self, storage_path: str):
			return None

	class FakeStorage:
		async def delete(self, storage_key):
			pass

	class FakeLLM:
		async def extract_knowledge(self, chunk_text):
			from core.domain.entities.knowledge import KnowledgeExtractionResult
			return KnowledgeExtractionResult(entities=[], facts=[], events=[], locations=[])

	return {
		"parser": FakeParser(),
		"storage": FakeStorage(),
		"llm_provider": FakeLLM(),
		"_repository": repository,
	}


def configure_worker(monkeypatch, repository: FakeRepository) -> None:
	monkeypatch.setattr(worker_module, "session_factory", lambda: FakeSessionContext())
	monkeypatch.setattr(
		worker_module,
		"PostgresBookRepository",
		lambda session: repository,
	)
	monkeypatch.setattr(
		worker_module,
		"PostgresKnowledgeRepository",
		lambda session: FakeKnowledgeRepository(),
	)
	monkeypatch.setattr(worker_module, "chunk_chapters", lambda chapters: ["chunk"])


def test_worker_marks_corrupt_epub_failed_without_retry(monkeypatch) -> None:
	repository = FakeRepository()
	configure_worker(monkeypatch, repository)
	ctx = make_ctx(repository, parser_error=ValueError("corrupt EPUB"))

	asyncio.run(worker_module.process_ebook(ctx, "book-123", "books/book-123.epub"))

	assert repository.calls == [
		("processing", "book-123"),
		("failed", "corrupt EPUB"),
	]


def test_worker_reraises_processing_failure_for_arq_retry(monkeypatch) -> None:
	repository = FakeRepository(RuntimeError("database unavailable"))
	configure_worker(monkeypatch, repository)
	ctx = make_ctx(repository)

	with pytest.raises(RuntimeError, match="database unavailable"):
		asyncio.run(
			worker_module.process_ebook(ctx, "book-123", "books/book-123.epub")
		)

	assert repository.calls == [
		("processing", "book-123"),
		("failed", "database unavailable"),
	]


def test_worker_allows_three_attempts_for_retryable_jobs() -> None:
	assert worker_module.WorkerSettings.max_tries == 3


def test_worker_connects_to_the_configured_redis() -> None:
	redis_settings = worker_module.WorkerSettings.redis_settings

	assert redis_settings.host == urlparse(settings.redis_url).hostname
	assert redis_settings.port == urlparse(settings.redis_url).port


def test_worker_settings_registers_the_graph_generation_job() -> None:
	assert worker_module.generate_graph in worker_module.WorkerSettings.functions


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

	async def get_graph_state(self, book_id: str):
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
	from core.domain.entities.graph import BookGraphState

	return BookGraphState(
		book_id="book-123",
		progress_position=0.4,
		processing_status=processing_status,
		graph_revision=0,
	)


def run_graph_job(monkeypatch, repository) -> None:
	monkeypatch.setattr(worker_module, "session_factory", lambda: FakeSessionContext())
	monkeypatch.setattr(
		worker_module, "PostgresBookRepository", lambda session: repository
	)
	monkeypatch.setattr(
		worker_module, "PostgresKnowledgeRepository", lambda session: repository
	)
	asyncio.run(worker_module.generate_graph({"llm_provider": object()}, "book-123"))


def test_graph_job_applies_a_new_resolution_and_bumps_the_revision(monkeypatch) -> None:
	repository = FakeGraphBookRepository(
		state=graph_state(),
		candidates=[candidate("e1", "Alice", 0.1), candidate("e2", "Alice", 0.7)],
	)

	run_graph_job(monkeypatch, repository)

	assert repository.applied == [{"e1": "e1", "e2": "e1"}]
	assert repository.revision_bumps == ["book-123"]


def test_graph_job_skips_the_revision_when_the_resolution_is_unchanged(monkeypatch) -> None:
	repository = FakeGraphBookRepository(
		state=graph_state(),
		candidates=[candidate("e1", "Alice", 0.1)],
		stored={"e1": ("e1", "deterministic")},
	)

	run_graph_job(monkeypatch, repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_skips_a_book_that_is_not_ready(monkeypatch) -> None:
	repository = FakeGraphBookRepository(
		state=graph_state(processing_status="processing"),
		candidates=[candidate("e1", "Alice", 0.1)],
	)

	run_graph_job(monkeypatch, repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_skips_an_unknown_book(monkeypatch) -> None:
	repository = FakeGraphBookRepository(state=None, candidates=[candidate("e1", "Alice")])

	run_graph_job(monkeypatch, repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_skips_a_book_without_mentions(monkeypatch) -> None:
	repository = FakeGraphBookRepository(state=graph_state(), candidates=[])

	run_graph_job(monkeypatch, repository)

	assert repository.applied == []
	assert repository.revision_bumps == []


def test_graph_job_swallows_a_resolution_failure_without_raising(monkeypatch) -> None:
	book_repository = FakeGraphBookRepository(state=graph_state())
	monkeypatch.setattr(worker_module, "session_factory", lambda: FakeSessionContext())
	monkeypatch.setattr(
		worker_module, "PostgresBookRepository", lambda session: book_repository
	)
	monkeypatch.setattr(
		worker_module, "PostgresKnowledgeRepository", lambda session: ExplodingKnowledgeRepository()
	)

	asyncio.run(worker_module.generate_graph({"llm_provider": object()}, "book-123"))

	assert book_repository.applied == []
	assert book_repository.revision_bumps == []
