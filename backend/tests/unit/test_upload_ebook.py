import asyncio
import hashlib

import pytest

from core.application.use_cases.process_ebook import (
    EbookTooLargeError,
    InvalidEbookError,
    UploadEbookUseCase,
)
from core.ports.ebook_metadata import EbookMetadata
from tests.fixtures.epub import valid_epub_bytes


class FakeMetadataReader:
    def __init__(self, title: str | None = None, author: str | None = None) -> None:
        self.metadata = EbookMetadata(title=title, author=author)

    async def read_metadata(self, storage_path: str) -> EbookMetadata:
        return self.metadata


class FakeBookRepository:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.created = None
        self.pending: list[str] = []
        self.metadata: list[tuple[str, str | None, str | None]] = []

    async def get_by_document_hash(self, document_hash: str):
        return self.existing

    async def get_or_create(self, book_id: str, document_hash: str, storage_key: str):
        if self.existing is not None:
            return self.existing, False
        self.created = type(
            "Book",
            (),
            {
                "id": book_id,
                "document_hash": document_hash,
                "storage_key": storage_key,
                "processing_status": "pending",
                "title": None,
                "author": None,
            },
        )()
        return self.created, True

    async def mark_pending(self, book_id: str) -> None:
        self.pending.append(book_id)

    async def set_metadata(
        self, book_id: str, title: str | None, author: str | None
    ) -> None:
        self.metadata.append((book_id, title, author))


class FakeLibraryRepository:
    def __init__(self) -> None:
        self.linked: list[tuple[str, str]] = []

    async def link(self, owner_id: str, book_id: str) -> None:
        self.linked.append((owner_id, book_id))


class FakeStorage:
    def __init__(self) -> None:
        self.saved = None

    async def save(self, storage_key: str, content: bytes) -> str:
        self.saved = (storage_key, content)
        return storage_key

    async def delete(self, storage_key: str) -> None:
        pass


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued = None

    async def enqueue(self, book_id: str, storage_key: str) -> None:
        self.enqueued = (book_id, storage_key)


def test_upload_stores_md5_and_enqueues_processing() -> None:
    content = valid_epub_bytes()
    repository = FakeBookRepository()
    storage = FakeStorage()
    queue = FakeQueue()
    library = FakeLibraryRepository()
    use_case = UploadEbookUseCase(
        repository, storage, queue, library, FakeMetadataReader()
    )

    result = asyncio.run(use_case.execute(content, "owner-1"))

    assert result.document_hash == hashlib.md5(content).hexdigest()
    assert result.processing_status == "pending"
    assert repository.created.document_hash == result.document_hash
    assert storage.saved == (f"books/{result.book_id}.epub", content)
    assert queue.enqueued == (result.book_id, repository.created.storage_key)
    assert library.linked == [("owner-1", result.book_id)]


def test_upload_reuses_existing_book_without_reprocessing() -> None:
    existing = type(
        "Book",
        (),
        {
            "id": "existing-book",
            "document_hash": "known-hash",
            "storage_key": "books/existing-book.epub",
            "processing_status": "ready",
            "title": "Known title",
            "author": "Known author",
        },
    )()
    repository = FakeBookRepository(existing)
    storage = FakeStorage()
    queue = FakeQueue()
    library = FakeLibraryRepository()
    use_case = UploadEbookUseCase(
        repository, storage, queue, library, FakeMetadataReader()
    )

    content = valid_epub_bytes()
    repository.existing.document_hash = hashlib.md5(content).hexdigest()
    result = asyncio.run(use_case.execute(content, "owner-1"))

    assert result.book_id == "existing-book"
    assert storage.saved is None
    assert queue.enqueued is None
    assert library.linked == [("owner-1", "existing-book")]


def test_reuploading_a_failed_book_reprocesses_it_in_place() -> None:
    existing = type(
        "Book",
        (),
        {
            "id": "existing-book",
            "document_hash": "known-hash",
            "storage_key": "books/existing-book.epub",
            "processing_status": "failed",
            "title": None,
            "author": None,
        },
    )()
    repository = FakeBookRepository(existing)
    storage = FakeStorage()
    queue = FakeQueue()
    library = FakeLibraryRepository()
    use_case = UploadEbookUseCase(
        repository, storage, queue, library, FakeMetadataReader()
    )

    content = valid_epub_bytes()
    repository.existing.document_hash = hashlib.md5(content).hexdigest()
    result = asyncio.run(use_case.execute(content, "owner-1"))

    assert result.book_id == "existing-book"
    assert result.processing_status == "pending"
    assert repository.pending == ["existing-book"]
    assert queue.enqueued == ("existing-book", "books/existing-book.epub")
    assert library.linked == [("owner-1", "existing-book")]


def test_upload_rejects_non_epub_content() -> None:
    use_case = UploadEbookUseCase(
        FakeBookRepository(),
        FakeStorage(),
        FakeQueue(),
        FakeLibraryRepository(),
        FakeMetadataReader(),
    )

    with pytest.raises(InvalidEbookError):
        asyncio.run(use_case.execute(b"not an epub", "owner-1"))


def test_upload_rejects_structurally_invalid_epub_archive() -> None:
    use_case = UploadEbookUseCase(
        FakeBookRepository(),
        FakeStorage(),
        FakeQueue(),
        FakeLibraryRepository(),
        FakeMetadataReader(),
    )

    with pytest.raises(InvalidEbookError):
        asyncio.run(use_case.execute(b"PK\x03\x04", "owner-1"))


def test_upload_rejects_content_above_configured_limit() -> None:
    content = valid_epub_bytes()
    use_case = UploadEbookUseCase(
        FakeBookRepository(),
        FakeStorage(),
        FakeQueue(),
        FakeLibraryRepository(),
        FakeMetadataReader(),
        max_size_bytes=len(content) - 1,
    )

    with pytest.raises(EbookTooLargeError):
        asyncio.run(use_case.execute(content, "owner-1"))
