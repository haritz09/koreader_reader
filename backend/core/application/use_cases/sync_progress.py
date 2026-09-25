"""Use case for synchronizing normalized reading progress."""

from core.domain.entities.reading_progress import ReadingProgress
from core.ports.reading_progress_provider import ReadingProgressProvider
from core.ports.reading_progress_store import ReadingProgressStore


class BookNotFoundError(Exception):
	"""Raised when a client document cannot be mapped to a book."""


class SyncProgressUseCase:
	def __init__(
		self,
		provider: ReadingProgressProvider,
		progress_store: ReadingProgressStore,
	) -> None:
		self._provider = provider
		self._progress_store = progress_store

	async def execute(self, document_hash: str, position: float) -> ReadingProgress:
		progress = await self._provider.resolve_progress(document_hash, position)
		if progress is None:
			raise BookNotFoundError(document_hash)
		await self._progress_store.update_progress(progress.book_id, position)
		return progress
