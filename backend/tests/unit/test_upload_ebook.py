import asyncio
import hashlib

import pytest

from core.application.use_cases.process_ebook import (
    EbookTooLargeError,
    InvalidEbookError,
    UploadEbookUseCase,
)
from tests.fixtures.epub import valid_epub_bytes


class FakeBookRepository:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.created = None

    async def get_by_document_hash(self, document_hash: str):
        return self.existing

    async def create(self, book_id: str, document_hash: str, storage_key: str):
        self.created = type(
            "Book",
            (),
            {
                "id": book_id,
                "document_hash": document_hash,
                "storage_key": storage_key,
                "processing_status": "pending",
            },
        )()
        return self.created


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
    use_case = UploadEbookUseCase(repository, storage, queue)

    result = asyncio.run(use_case.execute(content))

    assert result.document_hash == hashlib.md5(content).hexdigest()
    assert result.processing_status == "pending"
    assert repository.created.document_hash == result.document_hash
    assert storage.saved == (f"books/{result.book_id}.epub", content)
    assert queue.enqueued == (result.book_id, repository.created.storage_key)


def test_upload_reuses_existing_book_without_reprocessing() -> None:
    existing = type(
        "Book",
        (),
        {
            "id": "existing-book",
            "document_hash": "known-hash",
            "processing_status": "ready",
        },
    )()
    repository = FakeBookRepository(existing)
    storage = FakeStorage()
    queue = FakeQueue()
    use_case = UploadEbookUseCase(repository, storage, queue)

    content = valid_epub_bytes()
    repository.existing.document_hash = hashlib.md5(content).hexdigest()
    result = asyncio.run(use_case.execute(content))

    assert result.book_id == "existing-book"
    assert storage.saved is None
    assert queue.enqueued is None


def test_upload_rejects_non_epub_content() -> None:
    use_case = UploadEbookUseCase(FakeBookRepository(), FakeStorage(), FakeQueue())

    with pytest.raises(InvalidEbookError):
        asyncio.run(use_case.execute(b"not an epub"))


def test_upload_rejects_structurally_invalid_epub_archive() -> None:
    use_case = UploadEbookUseCase(FakeBookRepository(), FakeStorage(), FakeQueue())

    with pytest.raises(InvalidEbookError):
        asyncio.run(use_case.execute(b"PK\x03\x04"))


def test_upload_rejects_content_above_configured_limit() -> None:
    content = valid_epub_bytes()
    use_case = UploadEbookUseCase(
        FakeBookRepository(),
        FakeStorage(),
        FakeQueue(),
        max_size_bytes=len(content) - 1,
    )

    with pytest.raises(EbookTooLargeError):
        asyncio.run(use_case.execute(content))