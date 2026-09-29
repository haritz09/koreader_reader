from pydantic import BaseModel


class EbookUploadResponse(BaseModel):
    book_id: str
    document_hash: str
    processing_status: str


class EbookStatusResponse(EbookUploadResponse):
    progress_position: float
    processing_error: str | None = None
