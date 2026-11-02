"""Use case for retrying incomplete ebook processing."""

from dataclasses import dataclass

from core.domain.status import PENDING, RETRYABLE_STATUSES
from core.ports.book_repository import BookRepository
from core.ports.job_queue import EbookProcessingQueue


class BookNotFoundError(Exception):
	"""Raised when the book does not exist."""


class BookNotRetryableError(Exception):
	"""Raised when the book is not failed or partial."""


@dataclass(frozen=True)
class RetryResult:
	book_id: str
	processing_status: str


class RetryEbookUseCase:
	def __init__(
		self,
		repository: BookRepository,
		queue: EbookProcessingQueue,
	):
		self._repository = repository
		self._queue = queue

	async def execute(self, book_id: str) -> RetryResult:
		book = await self._repository.get_by_id(book_id)
		if book is None:
			raise BookNotFoundError(f"Book {book_id} not found")
		if book.processing_status not in RETRYABLE_STATUSES:
			raise BookNotRetryableError(
				f"Book {book_id} is not retryable (current: {book.processing_status})"
			)

		await self._repository.mark_processing(book_id)
		await self._queue.enqueue(book_id, book.storage_key)
		return RetryResult(book_id=book_id, processing_status=PENDING)
