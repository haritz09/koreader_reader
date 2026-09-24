"""Use case for synchronizing normalized reading progress."""

from core.domain.entities.reading_progress import ReadingProgress
from core.ports.reading_progress_provider import ReadingProgressProvider


class BookNotFoundError(Exception):
	"""Raised when a client document cannot be mapped to a book."""


class SyncProgressUseCase:
	def __init__(self, provider: ReadingProgressProvider) -> None:
		self._provider = provider

	async def execute(self, document_hash: str, position: float) -> ReadingProgress:
		progress = await self._provider.resolve_progress(document_hash, position)
		if progress is None:
			raise BookNotFoundError(document_hash)
		return progress
