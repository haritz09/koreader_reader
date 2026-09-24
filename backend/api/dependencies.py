"""FastAPI dependency providers."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.koreader.progress_provider import KoreaderProgressAdapter
from core.application.use_cases.sync_progress import SyncProgressUseCase
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import get_db_session


def get_book_repository(
	session: AsyncSession = Depends(get_db_session),
) -> PostgresBookRepository:
	return PostgresBookRepository(session)


def get_koreader_progress_adapter(
	book_repository: PostgresBookRepository = Depends(get_book_repository),
) -> KoreaderProgressAdapter:
	return KoreaderProgressAdapter(book_repository)


def get_sync_progress_use_case(
	adapter: KoreaderProgressAdapter = Depends(get_koreader_progress_adapter),
) -> SyncProgressUseCase:
	return SyncProgressUseCase(adapter)
