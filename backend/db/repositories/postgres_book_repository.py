"""Book repository implementation for postgres."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.book import Book
from db.models.knowledge import ChapterRecord, ChunkRecord


class PostgresBookRepository:
	def __init__(self, session: AsyncSession) -> None:
		self._session = session

	async def resolve_book_id(self, document_hash: str) -> str | None:
		result = await self._session.execute(
			select(Book.id).where(Book.document_hash == document_hash)
		)
		return result.scalar_one_or_none()

	async def update_progress(self, book_id: str, position: float) -> None:
		book = await self.get_by_id(book_id)
		if book is None:
			return
		book.progress_position = position
		await self._session.commit()

	async def get_by_document_hash(self, document_hash: str) -> Book | None:
		result = await self._session.execute(
			select(Book).where(Book.document_hash == document_hash)
		)
		return result.scalar_one_or_none()

	async def create(
		self,
		book_id: str,
		document_hash: str,
		storage_key: str,
	) -> Book:
		book = Book(
			id=book_id,
			document_hash=document_hash,
			storage_key=storage_key,
		)
		self._session.add(book)
		await self._session.commit()
		await self._session.refresh(book)
		return book

	async def get_by_id(self, book_id: str) -> Book | None:
		result = await self._session.execute(select(Book).where(Book.id == book_id))
		return result.scalar_one_or_none()

	async def mark_processing(self, book_id: str) -> None:
		book = await self.get_by_id(book_id)
		if book is None:
			return
		book.processing_status = "processing"
		book.processing_error = None
		await self._session.commit()

	async def replace_derived_content(
		self,
		book_id: str,
		chapters: list,
		chunks: list,
	) -> None:
		await self._session.execute(
			ChunkRecord.__table__.delete().where(ChunkRecord.book_id == book_id)
		)
		await self._session.execute(
			ChapterRecord.__table__.delete().where(ChapterRecord.book_id == book_id)
		)
		self._session.add_all(
			ChapterRecord(
				id=chapter.chapter_id,
				book_id=book_id,
				title=chapter.title,
				chapter_index=chapter.chapter_index,
			)
			for chapter in chapters
		)
		self._session.add_all(
			ChunkRecord(
				book_id=book_id,
				chapter_id=chunk.chapter_id,
				chunk_index=chunk.chunk_index,
				text=chunk.text,
				start_pctg=chunk.start_pctg,
				end_pctg=chunk.end_pctg,
			)
			for chunk in chunks
		)
		await self._session.commit()

	async def mark_ready(self, book_id: str) -> None:
		book = await self.get_by_id(book_id)
		if book is None:
			return
		book.processing_status = "ready"
		book.processing_error = None
		await self._session.commit()

	async def mark_failed(self, book_id: str, error: str) -> None:
		book = await self.get_by_id(book_id)
		if book is None:
			return
		book.processing_status = "failed"
		book.processing_error = error[:2000]
		await self._session.commit()
