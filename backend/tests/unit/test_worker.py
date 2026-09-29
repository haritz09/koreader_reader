import asyncio

import pytest

import workers.worker as worker_module


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


def configure_worker(monkeypatch, repository: FakeRepository, parser_error=None) -> None:
	monkeypatch.setattr(worker_module, "session_factory", lambda: FakeSessionContext())
	monkeypatch.setattr(
		worker_module,
		"PostgresBookRepository",
		lambda session: repository,
	)

	class FakeParser:
		async def parse(self, storage_path: str):
			if parser_error is not None:
				raise parser_error
			return ["chapter"]

	monkeypatch.setattr(worker_module, "EpubParser", FakeParser)
	monkeypatch.setattr(worker_module, "chunk_chapters", lambda chapters: ["chunk"])


def test_worker_marks_corrupt_epub_failed_without_retry(monkeypatch) -> None:
	repository = FakeRepository()
	configure_worker(monkeypatch, repository, ValueError("corrupt EPUB"))

	asyncio.run(worker_module.process_ebook({}, "book-123", "books/book-123.epub"))

	assert repository.calls == [
		("processing", "book-123"),
		("failed", "corrupt EPUB"),
	]


def test_worker_reraises_processing_failure_for_arq_retry(monkeypatch) -> None:
	repository = FakeRepository(RuntimeError("database unavailable"))
	configure_worker(monkeypatch, repository)

	with pytest.raises(RuntimeError, match="database unavailable"):
		asyncio.run(
			worker_module.process_ebook({}, "book-123", "books/book-123.epub")
		)

	assert repository.calls == [
		("processing", "book-123"),
		("failed", "database unavailable"),
	]


def test_worker_allows_three_attempts_for_retryable_jobs() -> None:
	assert worker_module.WorkerSettings.max_tries == 3