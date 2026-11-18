from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from api.dependencies import (
	get_book_cover_use_case,
	get_current_owner,
	get_delete_ebook_use_case,
	get_ebook_status_use_case,
	get_list_ebooks_use_case,
	get_retry_ebook_use_case,
	get_stream_book_status_use_case,
	get_stream_position_events_use_case,
	get_upload_ebook_use_case,
)
from api.presenters.ebooks import (
	book_list_response,
	book_status_response,
	cover_response,
	retry_response,
	upload_response,
)
from api.presenters.sse import (
	error_event_response,
	position_stream_response,
	status_stream_response,
)
from api.schemas.ebooks import EbookListResponse, EbookStatusResponse, EbookUploadResponse
from core.application.use_cases.browse_library import (
	GetEbookStatusUseCase,
	ListEbooksUseCase,
)
from core.application.use_cases.delete_ebook import DeleteEbookUseCase
from core.application.use_cases.get_book_cover import GetBookCoverUseCase
from core.application.use_cases.process_ebook import (
	EbookTooLargeError,
	InvalidEbookError,
	UploadEbookUseCase,
)
from core.application.use_cases.retry_ebook import (
	BookNotRetryableError,
	RetryEbookUseCase,
)
from core.application.use_cases.stream_book_status import StreamBookStatusUseCase
from core.application.use_cases.stream_position_events import (
	StreamPositionEventsUseCase,
)
from core.domain.errors import BookNotFoundError, BookProcessingError, CoverNotFoundError

router = APIRouter(prefix="/ebooks", tags=["ebooks"])


@router.get("", response_model=EbookListResponse)
async def list_ebooks(
	owner_id: str = Depends(get_current_owner),
	use_case: ListEbooksUseCase = Depends(get_list_ebooks_use_case),
) -> EbookListResponse:
	books = await use_case.execute(owner_id)
	return book_list_response(books)


@router.get(
	"/{book_id}",
	response_model=EbookStatusResponse,
	response_model_exclude_none=True,
)
async def get_ebook_status(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	use_case: GetEbookStatusUseCase = Depends(get_ebook_status_use_case),
) -> EbookStatusResponse:
	try:
		book = await use_case.execute(owner_id, book_id)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
		) from error
	return book_status_response(book)


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

	return upload_response(result)


@router.post("/{book_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_ebook(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	use_case: RetryEbookUseCase = Depends(get_retry_ebook_use_case),
) -> EbookUploadResponse:
	try:
		result = await use_case.execute(owner_id, book_id)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
		) from error
	except BookNotRetryableError as error:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=str(error),
		) from error

	return retry_response(result)


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
	use_case: StreamPositionEventsUseCase = Depends(get_stream_position_events_use_case),
) -> StreamingResponse:
	try:
		events = await use_case.execute(owner_id, book_id)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
		) from error
	return position_stream_response(events)


@router.get("/{book_id}/cover")
async def get_book_cover(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	use_case: GetBookCoverUseCase = Depends(get_book_cover_use_case),
) -> FileResponse:
	try:
		cover_path = await use_case.execute(owner_id, book_id)
	except CoverNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
		) from error
	return cover_response(cover_path)


@router.get("/{book_id}/events")
async def book_events(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	use_case: StreamBookStatusUseCase = Depends(get_stream_book_status_use_case),
) -> StreamingResponse:
	try:
		events = await use_case.execute(owner_id, book_id)
	except BookNotFoundError:
		return error_event_response("Book not found")
	return status_stream_response(events)
