from fastapi.testclient import TestClient

from api.dependencies import get_delete_ebook_use_case
from core.domain.errors import BookNotFoundError, BookProcessingError
from main import app
from tests.conftest import TEST_OWNER_ID


class FakeDeleteUseCase:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def execute(self, owner_id: str, book_id: str) -> None:
        self.calls.append((owner_id, book_id))
        if self.error is not None:
            raise self.error


def client_for(use_case: FakeDeleteUseCase) -> TestClient:
    app.dependency_overrides[get_delete_ebook_use_case] = lambda: use_case
    return TestClient(app)


def test_delete_returns_no_content_and_delegates_to_the_caller_owner() -> None:
    use_case = FakeDeleteUseCase()
    client = client_for(use_case)

    try:
        response = client.delete("/api/v1/ebooks/book-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert use_case.calls == [(TEST_OWNER_ID, "book-1")]


def test_delete_returns_not_found_for_an_unknown_or_unowned_book() -> None:
    client = client_for(FakeDeleteUseCase(BookNotFoundError("book-1")))

    try:
        response = client.delete("/api/v1/ebooks/book-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Book not found"}


def test_delete_conflicts_while_the_book_is_processing() -> None:
    client = client_for(FakeDeleteUseCase(BookProcessingError("book-1")))

    try:
        response = client.delete("/api/v1/ebooks/book-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "processing" in response.json()["detail"]


def test_delete_requires_a_session() -> None:
    from api.dependencies import get_current_owner

    app.dependency_overrides.pop(get_current_owner, None)
    client = TestClient(app)

    response = client.delete("/api/v1/ebooks/book-1")

    assert response.status_code == 401
