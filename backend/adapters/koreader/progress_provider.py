"""KOReader Kosync progress adapter."""

from core.domain.entities.reading_progress import ReadingProgress
from core.ports.book_repository import BookRepository


class KoreaderProgressAdapter:
	def __init__(self, book_repository: BookRepository) -> None:
		self._book_repository = book_repository

	async def resolve_book_id(self, document_hash: str) -> str | None:
		return await self._book_repository.resolve_book_id(document_hash)

	async def resolve_progress(
		self,
		document_hash: str,
		position: float,
	) -> ReadingProgress | None:
		book_id = await self.resolve_book_id(document_hash)
		if book_id is None:
			return None
		return ReadingProgress(book_id=book_id, position=position)
