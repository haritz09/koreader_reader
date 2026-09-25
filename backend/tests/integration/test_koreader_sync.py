from fastapi.testclient import TestClient

from adapters.koreader.progress_provider import KoreaderProgressAdapter
from api.dependencies import get_book_repository, get_koreader_progress_adapter
from main import app


class InMemoryBookRepository:
    def __init__(self, books: dict[str, str]) -> None:
        self._books = books

    async def resolve_book_id(self, document_hash: str) -> str | None:
        return self._books.get(document_hash)

    async def update_progress(self, book_id: str, position: float) -> None:
        pass


def client_for_books(books: dict[str, str]) -> TestClient:
    repository = InMemoryBookRepository(books)
    app.dependency_overrides[get_book_repository] = lambda: repository
    app.dependency_overrides[get_koreader_progress_adapter] = lambda: (
        KoreaderProgressAdapter(repository)
    )
    return TestClient(app)


def test_sync_endpoint_returns_normalized_progress_for_known_document() -> None:
    client = client_for_books({"8374029a8f3b2e01": "book-123"})

    try:
        response = client.post(
            "/api/v1/adapters/koreader/sync",
            json={
                "document": "8374029a8f3b2e01",
                "progress": 0.374,
                "percentage": 37,
                "device": "kobo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {
        "book_id": "book-123",
        "position": 0.374,
        "device": "kobo",
        "accepted": True,
    }


def test_sync_endpoint_returns_not_found_for_unknown_document() -> None:
    client = client_for_books({})

    try:
        response = client.post(
            "/api/v1/adapters/koreader/sync",
            json={
                "document": "unknown",
                "progress": 0.374,
                "percentage": 37,
                "device": "kobo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_sync_endpoint_rejects_invalid_payloads() -> None:
    client = client_for_books({"document": "book-123"})
    invalid_payloads = [
        {"document": "document", "progress": -0.01, "percentage": 0, "device": "kobo"},
        {"document": "document", "progress": 1.01, "percentage": 100, "device": "kobo"},
        {"document": "", "progress": 0.5, "percentage": 50, "device": "kobo"},
        {"document": "document", "progress": 0.5, "percentage": 50, "device": ""},
        {
            "document": "document",
            "progress": 0.5,
            "percentage": 50,
            "device": "kobo",
            "unexpected": True,
        },
    ]

    try:
        responses = [
            client.post("/api/v1/adapters/koreader/sync", json=payload)
            for payload in invalid_payloads
        ]
    finally:
        app.dependency_overrides.clear()

    assert all(response.status_code == 422 for response in responses)