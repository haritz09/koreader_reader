import asyncio
from types import SimpleNamespace

from core.application.use_cases.retry_ebook import RetryEbookUseCase


class PartialBookRepository:
	async def get_by_id(self, book_id: str):
		return SimpleNamespace(
			id=book_id,
			storage_key="books/book-1.epub",
			processing_status="partial",
		)

	async def mark_processing(self, book_id: str) -> None:
		self.marked_processing = book_id


class RecordingQueue:
	def __init__(self) -> None:
		self.jobs: list[tuple[str, str]] = []

	async def enqueue(self, book_id: str, storage_key: str) -> None:
		self.jobs.append((book_id, storage_key))


def test_retry_accepts_partial_books_and_requeues_the_source() -> None:
	async def _run() -> None:
		repository = PartialBookRepository()
		queue = RecordingQueue()
		use_case = RetryEbookUseCase(repository, queue)

		result = await use_case.execute("book-1")

		assert result.processing_status == "pending"
		assert repository.marked_processing == "book-1"
		assert queue.jobs == [("book-1", "books/book-1.epub")]

	asyncio.run(_run())
