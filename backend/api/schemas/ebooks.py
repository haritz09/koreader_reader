from datetime import datetime

from pydantic import BaseModel


class EbookUploadResponse(BaseModel):
    book_id: str
    document_hash: str
    processing_status: str


class EbookStatusResponse(EbookUploadResponse):
    progress_position: float
    processing_error: str | None = None
    cover_url: str | None = None
    added_at: datetime
    last_synced_at: datetime | None = None


class EbookListResponse(BaseModel):
    books: list[EbookStatusResponse]
