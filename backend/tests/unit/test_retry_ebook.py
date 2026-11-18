import asyncio
from types import SimpleNamespace

import pytest

from core.application.use_cases.retry_ebook import (
	BookNotRetryableError,
	RetryEbookUseCase,
)
from core.domain.errors import BookNotFoundError


class FakeBookRepository:
	def __init__(self, status: str = "partial") -> None:
		self.status = status
		self.marked_processing: str | None = None

	async def get_by_id(self, book_id: str):
		return SimpleNamespace(
			id=book_id,
			storage_key="books/book-1.epub",
			processing_status=self.status,
		)

	async def mark_processing(self, book_id: str) -> None:
		self.marked_processing = book_id


class RecordingQueue:
	def __init__(self) -> None:
		self.jobs: list[tuple[str, str]] = []

	async def enqueue(self, book_id: str, storage_key: str) -> None:
		self.jobs.append((book_id, storage_key))


class FakeLibrary:
	def __init__(self, owned: bool = True) -> None:
		self.owned = owned

	async def get_book(self, owner_id: str, book_id: str):
		return object() if self.owned else None


def test_retry_accepts_partial_books_and_requeues_the_source() -> None:
	async def _run() -> None:
		repository = FakeBookRepository()
		queue = RecordingQueue()
		use_case = RetryEbookUseCase(repository, queue, FakeLibrary())

		result = await use_case.execute("owner-1", "book-1")

		assert result.processing_status == "pending"
		assert repository.marked_processing == "book-1"
		assert queue.jobs == [("book-1", "books/book-1.epub")]

	asyncio.run(_run())


def test_retry_refuses_a_book_outside_the_callers_library() -> None:
	async def _run() -> None:
		repository = FakeBookRepository()
		queue = RecordingQueue()
		use_case = RetryEbookUseCase(repository, queue, FakeLibrary(owned=False))

		with pytest.raises(BookNotFoundError):
			await use_case.execute("owner-2", "book-1")

		assert repository.marked_processing is None
		assert queue.jobs == []

	asyncio.run(_run())


def test_retry_refuses_a_book_that_is_not_failed_or_partial() -> None:
	async def _run() -> None:
		repository = FakeBookRepository(status="ready")
		queue = RecordingQueue()
		use_case = RetryEbookUseCase(repository, queue, FakeLibrary())

		with pytest.raises(BookNotRetryableError):
			await use_case.execute("owner-1", "book-1")

		assert repository.marked_processing is None
		assert queue.jobs == []

	asyncio.run(_run())
