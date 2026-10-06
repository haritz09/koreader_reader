from fastapi.testclient import TestClient

from adapters.koreader.progress_provider import KoreaderProgressAdapter
from api.dependencies import (
	get_book_repository,
	get_graph_generation_queue,
	get_koreader_progress_adapter,
)
from core.domain.entities.graph import BookGraphState
from main import app


class RecordingGraphQueue:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, book_id: str) -> None:
        self.enqueued.append(book_id)


class InMemoryBookRepository:
    def __init__(
        self,
        books: dict[str, str],
        progress_position: float = 0.0,
        graph_revision: int = 0,
    ) -> None:
        self._books = books
        self._progress_position = progress_position
        self._graph_revision = graph_revision

    async def resolve_book_id(self, document_hash: str) -> str | None:
        return self._books.get(document_hash)

    async def update_progress(self, book_id: str, position: float) -> None:
        self._progress_position = position

    async def get_graph_state(self, book_id: str) -> BookGraphState | None:
        if book_id not in self._books.values():
            return None
        return BookGraphState(
            book_id=book_id,
            progress_position=self._progress_position,
            processing_status="ready",
            graph_revision=self._graph_revision,
        )


def client_for_books(books: dict[str, str], **kwargs) -> TestClient:
    repository = InMemoryBookRepository(books, **kwargs)
    app.dependency_overrides[get_book_repository] = lambda: repository
    app.dependency_overrides[get_koreader_progress_adapter] = lambda: (
        KoreaderProgressAdapter(repository)
    )
    app.dependency_overrides[get_graph_generation_queue] = lambda: RecordingGraphQueue()
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
        "graph_revision": 0,
        "graph_generation_queued": True,
    }


def test_sync_endpoint_reports_the_current_graph_revision() -> None:
    client = client_for_books({"document": "book-123"}, graph_revision=4)

    try:
        response = client.post(
            "/api/v1/adapters/koreader/sync",
            json={
                "document": "document",
                "progress": 0.5,
                "percentage": 50,
                "device": "kobo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["graph_revision"] == 4


def test_sync_endpoint_does_not_queue_graph_generation_when_rewinding() -> None:
    client = client_for_books({"document": "book-123"}, progress_position=0.9)

    try:
        response = client.post(
            "/api/v1/adapters/koreader/sync",
            json={
                "document": "document",
                "progress": 0.2,
                "percentage": 20,
                "device": "kobo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["graph_generation_queued"] is False


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