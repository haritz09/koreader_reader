"""Book repository implementation for postgres."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.book import Book


class PostgresBookRepository:
	def __init__(self, session: AsyncSession) -> None:
		self._session = session

	async def resolve_book_id(self, document_hash: str) -> str | None:
		result = await self._session.execute(
			select(Book.id).where(Book.document_hash == document_hash)
		)
		return result.scalar_one_or_none()
