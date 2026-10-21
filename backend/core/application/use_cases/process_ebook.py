"""Use case for accepting an ebook upload into an owner's library."""

import hashlib
import io
import logging
import uuid
import zipfile
from dataclasses import dataclass

from core.ports.book_repository import BookRepository
from core.ports.ebook_metadata import EbookMetadataReader
from core.ports.ebook_storage import EbookStorage
from core.ports.job_queue import EbookProcessingQueue
from core.ports.library_repository import LibraryRepository

logger = logging.getLogger(__name__)


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
		library: LibraryRepository,
		metadata_reader: EbookMetadataReader,
		max_size_bytes: int = 10 * 1024 * 1024,
	):
		self._repository = repository
		self._storage = storage
		self._queue = queue
		self._library = library
		self._metadata_reader = metadata_reader
		self._max_size_bytes = max_size_bytes

	async def execute(self, content: bytes, owner_id: str) -> EbookUploadResult:
		if len(content) > self._max_size_bytes:
			raise EbookTooLargeError(
				f"Ebook exceeds the maximum size of {self._max_size_bytes} bytes"
			)

		if not self._is_valid_epub(content):
			raise InvalidEbookError("Uploaded file is not a valid EPUB archive")

		document_hash = hashlib.md5(content).hexdigest()
		existing = await self._repository.get_by_document_hash(document_hash)
		if existing is not None:
			return await self._add_existing(existing, content, owner_id)

		book_id = str(uuid.uuid4())
		storage_key = f"books/{book_id}.epub"
		saved_path = await self._storage.save(storage_key, content)
		book, created = await self._repository.get_or_create(
			book_id, document_hash, storage_key
		)

		if not created:
			try:
				await self._storage.delete(storage_key)
			except Exception:
				logger.warning(
					"Could not remove orphaned upload %s", storage_key, exc_info=True
				)
			return await self._add_existing(book, content, owner_id)

		await self._apply_metadata(book, saved_path)
		await self._library.link(owner_id, book.id)
		await self._queue.enqueue(book.id, book.storage_key)
		return EbookUploadResult(
			book_id=book.id,
			document_hash=book.document_hash,
			processing_status=book.processing_status,
		)

	async def _add_existing(
		self, book, content: bytes, owner_id: str
	) -> EbookUploadResult:
		await self._library.link(owner_id, book.id)
		if book.processing_status == "failed":
			saved_path = await self._storage.save(book.storage_key, content)
			await self._repository.mark_pending(book.id)
			await self._apply_metadata(book, saved_path)
			await self._queue.enqueue(book.id, book.storage_key)
			return EbookUploadResult(
				book_id=book.id,
				document_hash=book.document_hash,
				processing_status="pending",
			)
		if book.title is None:
			saved_path = await self._storage.save(book.storage_key, content)
			await self._apply_metadata(book, saved_path)
		return EbookUploadResult(
			book_id=book.id,
			document_hash=book.document_hash,
			processing_status=book.processing_status,
		)

	async def _apply_metadata(self, book, storage_path: str) -> None:
		try:
			metadata = await self._metadata_reader.read_metadata(storage_path)
		except Exception:
			logger.warning(
				"Could not read EPUB metadata for book %s", book.id, exc_info=True
			)
			return
		if metadata.title is None and metadata.author is None:
			return
		try:
			await self._repository.set_metadata(
				book.id, metadata.title, metadata.author
			)
		except Exception:
			logger.warning(
				"Could not store EPUB metadata for book %s", book.id, exc_info=True
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
