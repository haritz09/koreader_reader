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


def test_worker_settings_has_startup_hook() -> None:
	assert worker_module.WorkerSettings.on_startup is worker_module.startup


def test_worker_connects_to_the_configured_redis() -> None:
	redis_settings = worker_module.WorkerSettings.redis_settings

	assert redis_settings.host == urlparse(settings.redis_url).hostname
	assert redis_settings.port == urlparse(settings.redis_url).port
