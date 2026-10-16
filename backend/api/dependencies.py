"""FastAPI dependency providers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.auth.jwt_tokens import JwtTokenService
from adapters.koreader.progress_provider import KoreaderProgressAdapter
from adapters.queue.arq_graph_queue import ArqGraphGenerationQueue
from adapters.queue.arq_queue import ArqEbookProcessingQueue
from adapters.storage.local_ebook_storage import LocalEbookStorage
from core.application.use_cases.create_session import CreateAnonymousSessionUseCase
from core.application.use_cases.delete_ebook import DeleteEbookUseCase
from core.application.use_cases.get_book_graph import GetBookGraphUseCase
from core.application.use_cases.process_ebook import UploadEbookUseCase
from core.application.use_cases.retry_ebook import RetryEbookUseCase
from core.application.use_cases.sync_progress import SyncProgressUseCase
from core.config import settings
from core.ports.book_repository import BookRepository
from core.ports.ebook_storage import EbookStorage
from core.ports.graph_repository import GraphRepository
from core.ports.job_queue import EbookProcessingQueue, GraphGenerationQueue
from core.ports.knowledge_repository import KnowledgeRepository
from core.ports.library_repository import LibraryRepository, LibraryRepositoryFactory
from core.ports.reading_progress_provider import ReadingProgressProvider
from core.ports.token_service import TokenService
from core.ports.user_repository import UserRepository
from core.services.graph_assembly import GraphAssemblyService
from db.repositories.knowledge_repository import PostgresKnowledgeRepository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.repositories.postgres_graph_repository import PostgresGraphRepository
from db.repositories.postgres_library_repository import PostgresLibraryRepository
from db.repositories.postgres_user_repository import PostgresUserRepository
from db.session import get_db_session, session_factory


def get_ebook_storage() -> EbookStorage:
	return LocalEbookStorage(Path(settings.ebook_storage_path))


def get_ebook_processing_queue() -> EbookProcessingQueue:
	return ArqEbookProcessingQueue(settings.redis_url)


def get_graph_generation_queue() -> GraphGenerationQueue:
	return ArqGraphGenerationQueue(settings.redis_url)


def get_book_repository(
	session: AsyncSession = Depends(get_db_session),
) -> BookRepository:
	return PostgresBookRepository(session)


def get_knowledge_repository(
	session: AsyncSession = Depends(get_db_session),
) -> KnowledgeRepository:
	return PostgresKnowledgeRepository(session)


def get_graph_repository(
	session: AsyncSession = Depends(get_db_session),
) -> GraphRepository:
	return PostgresGraphRepository(session)


def get_user_repository(
	session: AsyncSession = Depends(get_db_session),
) -> UserRepository:
	return PostgresUserRepository(session)


def get_library_repository(
	session: AsyncSession = Depends(get_db_session),
) -> LibraryRepository:
	return PostgresLibraryRepository(session)


def get_library_repository_factory() -> LibraryRepositoryFactory:
	"""Hand a streaming endpoint a repository it owns for its own lifetime.

	The session opened here is not tied to the request scope, so it survives
	while the response body is produced.
	"""

	@asynccontextmanager
	async def open_library_repository() -> AsyncIterator[LibraryRepository]:
		async with session_factory() as session:
			yield PostgresLibraryRepository(session)

	return open_library_repository


def get_token_service() -> TokenService:
	return JwtTokenService(
		settings.jwt_secret,
		algorithm=settings.jwt_algorithm,
		ttl_days=settings.jwt_ttl_days,
	)


def get_current_owner(
	request: Request,
	tokens: TokenService = Depends(get_token_service),
) -> str:
	token = request.cookies.get(settings.session_cookie_name)
	if not token:
		authorization = request.headers.get("authorization", "")
		if authorization.lower().startswith("bearer "):
			token = authorization[7:].strip()

	if not token:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session"
		)

	owner_id = tokens.verify(token)
	if not owner_id:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
		)
	return owner_id


def get_create_session_use_case(
	users: UserRepository = Depends(get_user_repository),
) -> CreateAnonymousSessionUseCase:
	return CreateAnonymousSessionUseCase(users)


def get_delete_ebook_use_case(
	library: LibraryRepository = Depends(get_library_repository),
) -> DeleteEbookUseCase:
	return DeleteEbookUseCase(library)


def get_graph_assembly_service(
	graph_repository: GraphRepository = Depends(get_graph_repository),
) -> GraphAssemblyService:
	return GraphAssemblyService(graph_repository)


def get_koreader_progress_adapter(
	book_repository: BookRepository = Depends(get_book_repository),
) -> ReadingProgressProvider:
	return KoreaderProgressAdapter(book_repository)


def get_sync_progress_use_case(
	adapter: ReadingProgressProvider = Depends(get_koreader_progress_adapter),
	book_repository: BookRepository = Depends(get_book_repository),
	library: LibraryRepository = Depends(get_library_repository),
	graph_queue: GraphGenerationQueue = Depends(get_graph_generation_queue),
) -> SyncProgressUseCase:
	return SyncProgressUseCase(adapter, book_repository, library, graph_queue)


def get_book_graph_use_case(
	book_repository: BookRepository = Depends(get_book_repository),
	assembly: GraphAssemblyService = Depends(get_graph_assembly_service),
) -> GetBookGraphUseCase:
	return GetBookGraphUseCase(book_repository, assembly)


def get_upload_ebook_use_case(
	book_repository: BookRepository = Depends(get_book_repository),
	storage: EbookStorage = Depends(get_ebook_storage),
	queue: EbookProcessingQueue = Depends(get_ebook_processing_queue),
	library: LibraryRepository = Depends(get_library_repository),
) -> UploadEbookUseCase:
	return UploadEbookUseCase(
		book_repository,
		storage,
		queue,
		library,
		max_size_bytes=settings.max_ebook_size_bytes,
	)


def get_retry_ebook_use_case(
	book_repository: BookRepository = Depends(get_book_repository),
	queue: EbookProcessingQueue = Depends(get_ebook_processing_queue),
) -> RetryEbookUseCase:
	return RetryEbookUseCase(book_repository, queue)
