"""Library membership repository implementation for postgres."""

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.book import Book
from db.models.user_book import UserBookRecord


class PostgresLibraryRepository:
	"""Library membership repository backed by PostgreSQL.

	Reads use ``populate_existing`` so they always return the row as committed
	by other connections.
	"""

	def __init__(self, session: AsyncSession) -> None:
		self._session = session

	async def link(self, owner_id: str, book_id: str) -> None:
		"""Add a book to a library, restoring it when it was soft-deleted."""
		statement = pg_insert(UserBookRecord).values(
			owner_id=owner_id,
			book_id=book_id,
			deleted_at=None,
		)
		statement = statement.on_conflict_do_update(
			index_elements=[UserBookRecord.owner_id, UserBookRecord.book_id],
			set_={"deleted_at": None},
		)
		await self._session.execute(statement)
		await self._session.commit()

	async def get_book(self, owner_id: str, book_id: str) -> Book | None:
		result = await self._session.execute(
			select(Book)
			.join(UserBookRecord, UserBookRecord.book_id == Book.id)
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.deleted_at.is_(None))
			.where(Book.id == book_id)
			.execution_options(populate_existing=True)
		)
		return result.scalar_one_or_none()

	async def list_books(self, owner_id: str) -> list[Book]:
		result = await self._session.execute(
			select(Book)
			.join(UserBookRecord, UserBookRecord.book_id == Book.id)
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.deleted_at.is_(None))
			.order_by(UserBookRecord.added_at.desc(), Book.id)
			.execution_options(populate_existing=True)
		)
		return list(result.scalars().all())

	async def soft_delete(self, owner_id: str, book_id: str) -> bool:
		result = await self._session.execute(
			update(UserBookRecord)
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.book_id == book_id)
			.values(deleted_at=func.now())
		)
		await self._session.commit()
		return result.rowcount > 0
