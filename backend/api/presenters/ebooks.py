from pathlib import Path

from fastapi.responses import FileResponse

from adapters.storage.image_media_type import cover_media_type
from api.schemas.ebooks import (
    EbookListResponse,
    EbookStatusResponse,
    EbookUploadResponse,
)
from core.application.use_cases.process_ebook import EbookUploadResult
from core.application.use_cases.retry_ebook import RetryResult
from core.domain.entities.library import LibraryBook

COVER_CACHE_HEADER = {"Cache-Control": "private, max-age=3600"}


def progress_counts(
    chunks_total: int | None,
    chunks_extracted: int | None,
) -> tuple[int | None, int | None]:
    if not chunks_total:
        return None, None
    return chunks_total, chunks_extracted


def book_list_response(books: list[LibraryBook]) -> EbookListResponse:
    return EbookListResponse(books=[book_status_response(book) for book in books])


def book_status_response(book: LibraryBook) -> EbookStatusResponse:
    chunks_total, chunks_extracted = progress_counts(
        book.chunks_total,
        book.chunks_extracted,
    )
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
        chunks_total=chunks_total,
        chunks_extracted=chunks_extracted,
    )


def upload_response(result: EbookUploadResult) -> EbookUploadResponse:
    return EbookUploadResponse(
        book_id=result.book_id,
        document_hash=result.document_hash,
        processing_status=result.processing_status,
    )


def retry_response(result: RetryResult) -> EbookUploadResponse:
    return EbookUploadResponse(
        book_id=result.book_id,
        document_hash="",
        processing_status=result.processing_status,
    )


def cover_response(path: Path) -> FileResponse:
    return FileResponse(
        path,
        media_type=cover_media_type(path),
        headers=COVER_CACHE_HEADER,
    )
