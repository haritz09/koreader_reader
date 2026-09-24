import asyncio

from adapters.koreader.progress_provider import KoreaderProgressAdapter


class InMemoryBookRepository:
    def __init__(self, books: dict[str, str]) -> None:
        self._books = books

    async def resolve_book_id(self, document_hash: str) -> str | None:
        return self._books.get(document_hash)


def resolve_progress(
    books: dict[str, str],
    document_hash: str,
    position: float,
):
    adapter = KoreaderProgressAdapter(InMemoryBookRepository(books))
    return asyncio.run(adapter.resolve_progress(document_hash, position))


def test_known_koreader_document_becomes_domain_progress() -> None:
    progress = resolve_progress(
        {"8374029a8f3b2e01": "book-123"},
        "8374029a8f3b2e01",
        0.374,
    )

    assert progress is not None
    assert progress.book_id == "book-123"
    assert progress.position == 0.374


def test_unknown_koreader_document_has_no_book_mapping() -> None:
    progress = resolve_progress({}, "unknown", 0.374)

    assert progress is None


def test_adapter_preserves_progress_boundaries() -> None:
    for position in (0.0, 1.0):
        progress = resolve_progress({"document": "book-123"}, "document", position)

        assert progress is not None
        assert progress.position == position