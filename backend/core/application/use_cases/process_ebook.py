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


class EbookTooLargeError(Exception):
	"""Raised when an upload exceeds the configured size limit."""


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
		max_size_bytes: int = 10 * 1024 * 1024,
	):
		self._repository = repository
		self._storage = storage
		self._queue = queue
		self._max_size_bytes = max_size_bytes

	async def execute(self, content: bytes) -> EbookUploadResult:
		if len(content) > self._max_size_bytes:
			raise EbookTooLargeError(
				f"Ebook exceeds the maximum size of {self._max_size_bytes} bytes"
			)

		if not self._is_valid_epub(content):
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

	@staticmethod
	def _is_valid_epub(content: bytes) -> bool:
		if not content or not zipfile.is_zipfile(io.BytesIO(content)):
			return False

		try:
			with zipfile.ZipFile(io.BytesIO(content)) as archive:
				names = archive.namelist()
				return (
					bool(names)
					and names[0] == "mimetype"
					and archive.read("mimetype") == b"application/epub+zip"
					and "META-INF/container.xml" in names
				)
		except (KeyError, OSError, zipfile.BadZipFile):
			return False
