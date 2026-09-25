from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.dependencies import get_book_repository, get_upload_ebook_use_case
from api.schemas.ebooks import EbookStatusResponse, EbookUploadResponse
from core.application.use_cases.process_ebook import (
	EbookTooLargeError,
	InvalidEbookError,
	UploadEbookUseCase,
)

router = APIRouter(prefix="/ebooks", tags=["ebooks"])


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
"""Ebook upload and processing endpoints."""
