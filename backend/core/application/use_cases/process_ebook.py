"""Use case for accepting an ebook upload."""

import hashlib
import io
import uuid
import zipfile
from dataclasses import dataclass

from core.ports.ebook_storage import EbookStorage
from core.ports.book_repository import BookRepository
from core.ports.job_queue import EbookProcessingQueue


class InvalidEbookError(Exception):
	"""Raised when the uploaded content is not a valid EPUB archive."""


@dataclass(frozen=True)
class EbookUploadResult:
	book_id: str
	document_hash: str
	processing_status: str


class UploadEbookUseCase:
	def __init__(
		self,
		repository: BookRepository,
		storage: EbookStorage,
		queue: EbookProcessingQueue,
	):
		self._repository = repository
		self._storage = storage
		self._queue = queue

	async def execute(self, content: bytes) -> EbookUploadResult:
		if not content or not zipfile.is_zipfile(io.BytesIO(content)):
			raise InvalidEbookError("Uploaded file is not a valid EPUB archive")

		document_hash = hashlib.md5(content).hexdigest()
		existing = await self._repository.get_by_document_hash(document_hash)
		if existing is not None:
			return EbookUploadResult(
				book_id=existing.id,
				document_hash=existing.document_hash,
				processing_status=existing.processing_status,
			)

		book_id = str(uuid.uuid4())
		storage_key = f"books/{book_id}.epub"
		await self._storage.save(storage_key, content)
		book = await self._repository.create(book_id, document_hash, storage_key)
		await self._queue.enqueue(book.id, book.storage_key)
		return EbookUploadResult(
			book_id=book.id,
			document_hash=book.document_hash,
			processing_status=book.processing_status,
		)
