from fastapi.testclient import TestClient

from api.dependencies import get_library_repository, get_upload_ebook_use_case
from core.application.use_cases.process_ebook import EbookTooLargeError
from main import app
from tests.fixtures.epub import valid_epub_bytes


class FakeUploadUseCase:
    async def execute(self, content: bytes, owner_id: str):
        return type(
            "UploadResult",
            (),
            {
                "book_id": "book-123",
                "document_hash": "hash-123",
                "processing_status": "pending",
            },
        )()


def test_upload_endpoint_returns_book_identity_and_pending_status() -> None:
    app.dependency_overrides[get_upload_ebook_use_case] = (
        lambda: FakeUploadUseCase()
    )
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/ebooks",
            files={"file": ("book.epub", valid_epub_bytes(), "application/epub+zip")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {
        "book_id": "book-123",
        "document_hash": "hash-123",
        "processing_status": "pending",
    }


class FakeOversizedUploadUseCase:
    async def execute(self, content: bytes, owner_id: str):
        raise EbookTooLargeError("Ebook exceeds the maximum size of 10485760 bytes")


def test_upload_endpoint_returns_413_for_oversized_upload() -> None:
    app.dependency_overrides[get_upload_ebook_use_case] = (
        lambda: FakeOversizedUploadUseCase()
    )
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/ebooks",
            files={"file": ("book.epub", b"too large", "application/epub+zip")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Ebook exceeds the maximum size of 10485760 bytes"
    }


class FakeLibraryRepository:
    def __init__(self, book=None) -> None:
        self.book = book

    async def get_book(self, owner_id: str, book_id: str):
        if self.book is not None and self.book.id == book_id:
            return self.book
        return None

    async def list_books(self, owner_id: str):
        return [] if self.book is None else [self.book]


def test_status_endpoint_includes_processing_error_for_failed_book() -> None:
    book = type(
        "Book",
        (),
        {
            "id": "book-123",
            "document_hash": "hash-123",
            "processing_status": "failed",
            "progress_position": 0.25,
            "processing_error": "Parser failed",
            "cover_path": None,
        },
    )()
    app.dependency_overrides[get_library_repository] = lambda: FakeLibraryRepository(book)
    client = TestClient(app)

    try:
        response = client.get("/api/v1/ebooks/book-123")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "book_id": "book-123",
        "document_hash": "hash-123",
        "processing_status": "failed",
        "progress_position": 0.25,
        "processing_error": "Parser failed",
    }


def test_status_endpoint_omits_processing_error_for_pending_book() -> None:
    book = type(
        "Book",
        (),
        {
            "id": "book-123",
            "document_hash": "hash-123",
            "processing_status": "pending",
            "progress_position": 0.0,
            "processing_error": None,
            "cover_path": None,
        },
    )()
    app.dependency_overrides[get_library_repository] = lambda: FakeLibraryRepository(book)
    client = TestClient(app)

    try:
        response = client.get("/api/v1/ebooks/book-123")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "book_id": "book-123",
        "document_hash": "hash-123",
        "processing_status": "pending",
        "progress_position": 0.0,
    }


def test_status_endpoint_returns_not_found_for_unknown_book() -> None:
    app.dependency_overrides[get_library_repository] = lambda: FakeLibraryRepository()
    client = TestClient(app)

    try:
        response = client.get("/api/v1/ebooks/missing-book")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Book not found"}


def test_library_endpoint_returns_the_owners_books() -> None:
    book = type(
        "Book",
        (),
        {
            "id": "book-123",
            "document_hash": "hash-123",
            "processing_status": "ready",
            "progress_position": 0.5,
            "processing_error": None,
            "cover_path": None,
        },
    )()
    app.dependency_overrides[get_library_repository] = lambda: FakeLibraryRepository(book)
    client = TestClient(app)

    try:
        response = client.get("/api/v1/ebooks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["book_id"] for item in response.json()["books"]] == ["book-123"]


def test_library_endpoint_returns_an_empty_list_for_a_new_owner() -> None:
    app.dependency_overrides[get_library_repository] = lambda: FakeLibraryRepository()
    client = TestClient(app)

    try:
        response = client.get("/api/v1/ebooks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"books": []}
