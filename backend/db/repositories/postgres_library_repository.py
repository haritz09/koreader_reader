"""Library membership repository implementation for postgres."""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.library import LibraryBook, ReadingState
from db.models.book import Book
from db.models.user_book import UserBookRecord


class PostgresLibraryRepository:

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

	async def get_book(self, owner_id: str, book_id: str) -> LibraryBook | None:
		result = await self._session.execute(
			self._book_select()
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.deleted_at.is_(None))
			.where(Book.id == book_id)
		)
		row = result.one_or_none()
		return LibraryBook(**row._mapping) if row is not None else None

	async def list_books(self, owner_id: str) -> list[LibraryBook]:
		result = await self._session.execute(
			self._book_select()
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.deleted_at.is_(None))
			.order_by(UserBookRecord.added_at.desc(), Book.id)
		)
		return [LibraryBook(**row._mapping) for row in result.all()]

	async def soft_delete(self, owner_id: str, book_id: str) -> bool:
		result = await self._session.execute(
			update(UserBookRecord)
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.book_id == book_id)
			.values(deleted_at=func.now())
		)
		await self._session.commit()
		return result.rowcount > 0

	async def get_reading_state(
		self, owner_id: str, book_id: str
	) -> ReadingState | None:
		result = await self._session.execute(
			select(
				UserBookRecord.progress_position,
				UserBookRecord.last_synced_at,
				Book.processing_status,
				Book.graph_revision,
			)
			.select_from(UserBookRecord)
			.join(Book, Book.id == UserBookRecord.book_id)
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.book_id == book_id)
			.where(UserBookRecord.deleted_at.is_(None))
		)
		row = result.one_or_none()
		if row is None:
			return None
		return ReadingState(
			progress_position=row[0],
			last_synced_at=row[1],
			processing_status=row[2],
			graph_revision=row[3] or 0,
		)

	async def update_progress(
		self,
		owner_id: str,
		book_id: str,
		position: float,
		synced_at: datetime,
	) -> bool:
		result = await self._session.execute(
			update(UserBookRecord)
			.where(UserBookRecord.owner_id == owner_id)
			.where(UserBookRecord.book_id == book_id)
			.where(UserBookRecord.deleted_at.is_(None))
			.values(progress_position=position, last_synced_at=synced_at)
		)
		await self._session.commit()
		return result.rowcount > 0

	@staticmethod
	def _book_select():
		return (
			select(
				Book.id.label("book_id"),
				Book.document_hash,
				Book.processing_status,
				Book.processing_error,
				Book.cover_path,
				Book.title,
				Book.author,
				UserBookRecord.progress_position,
				UserBookRecord.added_at,
				UserBookRecord.last_synced_at,
			)
			.select_from(Book)
			.join(UserBookRecord, UserBookRecord.book_id == Book.id)
		)
