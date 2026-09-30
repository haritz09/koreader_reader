"""FastAPI dependency providers."""

from pathlib import Path

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.koreader.progress_provider import KoreaderProgressAdapter
from adapters.queue.arq_graph_queue import ArqGraphGenerationQueue
from adapters.queue.arq_queue import ArqEbookProcessingQueue
from adapters.storage.local_ebook_storage import LocalEbookStorage
from core.application.use_cases.get_book_graph import GetBookGraphUseCase
from core.application.use_cases.process_ebook import UploadEbookUseCase
from core.application.use_cases.sync_progress import SyncProgressUseCase
from core.config import settings
from core.ports.book_repository import BookRepository
from core.ports.ebook_storage import EbookStorage
from core.ports.job_queue import EbookProcessingQueue, GraphGenerationQueue
from core.services.graph_assembly import GraphAssemblyService
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.repositories.postgres_graph_repository import PostgresGraphRepository
from db.session import get_db_session


def get_ebook_storage() -> LocalEbookStorage:
	return LocalEbookStorage(Path(settings.ebook_storage_path))


def get_ebook_processing_queue() -> ArqEbookProcessingQueue:
	return ArqEbookProcessingQueue(settings.redis_url)


def get_graph_generation_queue() -> ArqGraphGenerationQueue:
	return ArqGraphGenerationQueue(settings.redis_url)


def get_book_repository(
	session: AsyncSession = Depends(get_db_session),
) -> PostgresBookRepository:
	return PostgresBookRepository(session)


def get_knowledge_repository(
	session: AsyncSession = Depends(get_db_session),
) -> PostgresKnowledgeRepository:
	return PostgresKnowledgeRepository(session)


def get_graph_repository(
	session: AsyncSession = Depends(get_db_session),
) -> PostgresGraphRepository:
	return PostgresGraphRepository(session)


def get_graph_assembly_service(
	graph_repository: PostgresGraphRepository = Depends(get_graph_repository),
) -> GraphAssemblyService:
	return GraphAssemblyService(graph_repository)


def get_koreader_progress_adapter(
	book_repository: BookRepository = Depends(get_book_repository),
) -> KoreaderProgressAdapter:
	return KoreaderProgressAdapter(book_repository)


def get_sync_progress_use_case(
	adapter: KoreaderProgressAdapter = Depends(get_koreader_progress_adapter),
	book_repository: BookRepository = Depends(get_book_repository),
	graph_queue: GraphGenerationQueue = Depends(get_graph_generation_queue),
) -> SyncProgressUseCase:
	return SyncProgressUseCase(adapter, book_repository, graph_queue)


def get_book_graph_use_case(
	book_repository: BookRepository = Depends(get_book_repository),
	assembly: GraphAssemblyService = Depends(get_graph_assembly_service),
) -> GetBookGraphUseCase:
	return GetBookGraphUseCase(book_repository, assembly)


def get_upload_ebook_use_case(
	book_repository: BookRepository = Depends(get_book_repository),
	storage: EbookStorage = Depends(get_ebook_storage),
	queue: EbookProcessingQueue = Depends(get_ebook_processing_queue),
) -> UploadEbookUseCase:
	return UploadEbookUseCase(
		book_repository,
		storage,
		queue,
		max_size_bytes=settings.max_ebook_size_bytes,
	)
