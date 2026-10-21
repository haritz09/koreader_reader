import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from api.dependencies import (
	get_current_owner,
	get_delete_ebook_use_case,
	get_library_repository,
	get_library_repository_factory,
	get_retry_ebook_use_case,
	get_upload_ebook_use_case,
)
from api.schemas.ebooks import EbookListResponse, EbookStatusResponse, EbookUploadResponse
from core.application.use_cases.delete_ebook import DeleteEbookUseCase
from core.application.use_cases.process_ebook import (
	EbookTooLargeError,
	InvalidEbookError,
	UploadEbookUseCase,
)
from core.application.use_cases.retry_ebook import (
	BookNotFailedError,
	RetryEbookUseCase,
	RetryResult,
)
from core.application.use_cases.retry_ebook import (
	BookNotFoundError as RetryBookNotFoundError,
)
from core.domain.entities.library import LibraryBook
from core.domain.errors import BookNotFoundError, BookProcessingError
from core.ports.library_repository import LibraryRepository, LibraryRepositoryFactory

router = APIRouter(prefix="/ebooks", tags=["ebooks"])

STATUS_POLL_SECONDS = 1.0


def _status_response(book: LibraryBook) -> EbookStatusResponse:
	return EbookStatusResponse(
		book_id=book.book_id,
		document_hash=book.document_hash,
		processing_status=book.processing_status,
		progress_position=book.progress_position,
		processing_error=book.processing_error,
		cover_url=f"/api/v1/ebooks/{book.book_id}/cover" if book.cover_path else None,
		added_at=book.added_at,
		last_synced_at=book.last_synced_at,
		title=book.title,
		author=book.author,
	)


@router.get("", response_model=EbookListResponse)
async def list_ebooks(
	owner_id: str = Depends(get_current_owner),
	library: LibraryRepository = Depends(get_library_repository),
) -> EbookListResponse:
	books = await library.list_books(owner_id)
	return EbookListResponse(books=[_status_response(book) for book in books])


@router.get(
	"/{book_id}",
	response_model=EbookStatusResponse,
	response_model_exclude_none=True,
)
async def get_ebook_status(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	library: LibraryRepository = Depends(get_library_repository),
) -> EbookStatusResponse:
	book = await library.get_book(owner_id, book_id)
	if book is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
	return _status_response(book)


@router.post("", response_model=EbookUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_ebook(
	file: UploadFile = File(...),
	owner_id: str = Depends(get_current_owner),
	use_case: UploadEbookUseCase = Depends(get_upload_ebook_use_case),
) -> EbookUploadResponse:
	try:
		result = await use_case.execute(await file.read(), owner_id)
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
	owner_id: str = Depends(get_current_owner),
	library: LibraryRepository = Depends(get_library_repository),
	use_case: RetryEbookUseCase = Depends(get_retry_ebook_use_case),
) -> EbookUploadResponse:
	if await library.get_book(owner_id, book_id) is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

	try:
		result: RetryResult = await use_case.execute(book_id)
	except RetryBookNotFoundError as error:
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


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ebook(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	use_case: DeleteEbookUseCase = Depends(get_delete_ebook_use_case),
) -> None:
	try:
		await use_case.execute(owner_id, book_id)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
		) from error
	except BookProcessingError as error:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT, detail=str(error)
		) from error


@router.get("/{book_id}/position-events")
async def book_position_events(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	library: LibraryRepository = Depends(get_library_repository),
) -> StreamingResponse:
	if await library.get_book(owner_id, book_id) is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

	from lib.events import subscribe, unsubscribe

	async def event_generator():
		queue = await subscribe(owner_id, book_id)
		try:
			while True:
				event = await queue.get()
				yield f"data: {json.dumps(event)}\n\n"
		except asyncio.CancelledError:
			pass
		finally:
			unsubscribe(owner_id, book_id, queue)

	return StreamingResponse(
		event_generator(),
		media_type="text/event-stream",
		headers={
			"Cache-Control": "no-cache",
			"Connection": "keep-alive",
		},
	)


@router.get("/{book_id}/cover")
async def get_book_cover(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	library: LibraryRepository = Depends(get_library_repository),
) -> FileResponse:
	book = await library.get_book(owner_id, book_id)
	if book is None or not book.cover_path:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")
	cover_path = Path(book.cover_path)
	if not cover_path.exists():
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover file not found")
	return FileResponse(
		cover_path,
		media_type=_cover_media_type(cover_path),
		headers={"Cache-Control": "private, max-age=3600"},
	)


def _cover_media_type(path: Path) -> str:
	with path.open("rb") as stream:
		header = stream.read(12)
	if header.startswith(b"\x89PNG\r\n\x1a\n"):
		return "image/png"
	if header.startswith(b"GIF8"):
		return "image/gif"
	if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
		return "image/webp"
	return "image/jpeg"


@router.get("/{book_id}/events")
async def book_events(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	open_library: LibraryRepositoryFactory = Depends(get_library_repository_factory),
) -> StreamingResponse:
	async def event_generator():
		last_status = None
		async with open_library() as library:
			while True:
				book = await library.get_book(owner_id, book_id)
				if book is None:
					yield f"data: {json.dumps({'type': 'error', 'message': 'Book not found'})}\n\n"
					break
				if book.processing_status != last_status:
					last_status = book.processing_status
					yield f"data: {json.dumps({'type': 'status', 'status': book.processing_status, 'error': book.processing_error})}\n\n"
					if book.processing_status in ("ready", "failed"):
						break
				await asyncio.sleep(STATUS_POLL_SECONDS)

	return StreamingResponse(
		event_generator(),
		media_type="text/event-stream",
		headers={
			"Cache-Control": "no-cache",
			"Connection": "keep-alive",
		},
	)
