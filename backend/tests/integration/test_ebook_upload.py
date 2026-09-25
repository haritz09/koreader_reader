import io
import zipfile

from fastapi.testclient import TestClient

from api.dependencies import get_upload_ebook_use_case
from main import app


def epub_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("chapter.xhtml", "<html><body>Text</body></html>")
    return buffer.getvalue()


class FakeUploadUseCase:
    async def execute(self, content: bytes):
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
            files={"file": ("book.epub", epub_bytes(), "application/epub+zip")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {
        "book_id": "book-123",
        "document_hash": "hash-123",
        "processing_status": "pending",
    }