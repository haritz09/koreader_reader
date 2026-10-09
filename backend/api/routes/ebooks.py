import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from api.dependencies import get_book_repository, get_retry_ebook_use_case, get_upload_ebook_use_case
from api.schemas.ebooks import EbookListResponse, EbookStatusResponse, EbookUploadResponse
from core.application.use_cases.process_ebook import (
	EbookTooLargeError,
	InvalidEbookError,
	UploadEbookUseCase,
)
from core.application.use_cases.retry_ebook import (
	BookNotFailedError,
	BookNotFoundError,
	RetryEbookUseCase,
	RetryResult,
)
from core.config import settings
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory

router = APIRouter(prefix="/ebooks", tags=["ebooks"])


@router.get("", response_model=EbookListResponse)
async def list_ebooks(
	book_repository=Depends(get_book_repository),
) -> EbookListResponse:
	books = await book_repository.list_all()
	return EbookListResponse(
		books=[
			EbookStatusResponse(
				book_id=book.id,
				document_hash=book.document_hash,
				processing_status=book.processing_status,
				progress_position=book.progress_position,
				processing_error=book.processing_error,
				cover_url=f"/api/v1/ebooks/{book.id}/cover" if book.cover_path else None,
			)
			for book in books
		]
	)


@router.get(
	"/{book_id}",
	response_model=EbookStatusResponse,
	response_model_exclude_none=True,
)
async def get_ebook_status(
	book_id: str,
	book_repository=Depends(get_book_repository),
) -> EbookStatusResponse:
	book = await book_repository.get_by_id(book_id)
	if book is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
	return EbookStatusResponse(
		book_id=book.id,
		document_hash=book.document_hash,
		processing_status=book.processing_status,
		progress_position=book.progress_position,
		processing_error=book.processing_error,
		cover_url=f"/api/v1/ebooks/{book.id}/cover" if book.cover_path else None,
	)


@router.post("", response_model=EbookUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_ebook(
	file: UploadFile = File(...),
	use_case: UploadEbookUseCase = Depends(get_upload_ebook_use_case),
) -> EbookUploadResponse:
	try:
		result = await use_case.execute(await file.read())
	except EbookTooLargeError as error:
		raise HTTPException(
			status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
			detail=str(error),
		) from error
	except InvalidEbookError as error:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=str(error),
		) from error

	return EbookUploadResponse(
		book_id=result.book_id,
		document_hash=result.document_hash,
		processing_status=result.processing_status,
	)


@router.post("/{book_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_ebook(
	book_id: str,
	use_case: RetryEbookUseCase = Depends(get_retry_ebook_use_case),
) -> EbookUploadResponse:
	try:
		result: RetryResult = await use_case.execute(book_id)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=str(error),
		) from error
	except BookNotFailedError as error:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=str(error),
		) from error

	return EbookUploadResponse(
		book_id=result.book_id,
		document_hash="",
		processing_status=result.processing_status,
	)


@router.get("/{book_id}/cover")
async def get_book_cover(
	book_id: str,
	book_repository=Depends(get_book_repository),
) -> FileResponse:
	book = await book_repository.get_by_id(book_id)
	if book is None or not book.cover_path:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")
	cover_path = Path(book.cover_path)
	if not cover_path.exists():
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover file not found")
	return FileResponse(cover_path, media_type="image/jpeg")


@router.get("/{book_id}/events")
async def book_events(
	book_id: str,
) -> StreamingResponse:
	async def event_generator():
		async with session_factory() as session:
			repository = PostgresBookRepository(session)
			last_status = None
			while True:
				book = await repository.get_by_id(book_id)
				if book is None:
					yield f"data: {json.dumps({'type': 'error', 'message': 'Book not found'})}\n\n"
					break
				if book.processing_status != last_status:
					last_status = book.processing_status
					yield f"data: {json.dumps({'type': 'status', 'status': book.processing_status, 'error': book.processing_error})}\n\n"
					if book.processing_status in ("ready", "failed"):
						break
				await asyncio.sleep(1)

	return StreamingResponse(
		event_generator(),
		media_type="text/event-stream",
		headers={
			"Cache-Control": "no-cache",
			"Connection": "keep-alive",
		},
	)
"""Ebook upload and processing endpoints."""
