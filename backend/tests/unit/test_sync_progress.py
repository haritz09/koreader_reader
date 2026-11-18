import asyncio

import pytest

from core.application.use_cases.sync_progress import SyncProgressUseCase
from core.domain.entities.reading_progress import ReadingProgress
from core.domain.errors import BookNotFoundError as DomainBookNotFoundError
from tests.fixtures.repositories import FakeLibraryRepository, reading_state


class StubProgressProvider:
    def __init__(self, known_hash: str = "document-hash") -> None:
        self._known_hash = known_hash

    async def resolve_progress(self, document_hash: str, position: float) -> ReadingProgress | None:
        if document_hash != self._known_hash:
            return None
        return ReadingProgress(book_id="book-1", position=position)


class RecordingGraphQueue:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, book_id: str) -> None:
        self.enqueued.append(book_id)


class FailingGraphQueue:
    async def enqueue(self, book_id: str) -> None:
        raise RuntimeError("redis unavailable")


def sync(
    library: FakeLibraryRepository,
    queue=None,
    position: float = 0.5,
    document_hash: str = "document-hash",
):
    use_case = SyncProgressUseCase(StubProgressProvider(), library, queue)
    return asyncio.run(use_case.execute(document_hash, position, "owner-1"))


def test_moving_forward_queues_graph_generation() -> None:
    library = FakeLibraryRepository(reading_state(0.2))
    queue = RecordingGraphQueue()

    result = sync(library, queue, position=0.5)

    assert queue.enqueued == ["book-1"]
    assert result.graph_generation_queued is True
    assert library.updates == [("book-1", 0.5)]


def test_moving_forward_updates_a_partial_books_graph() -> None:
    library = FakeLibraryRepository(reading_state(0.2, processing_status="partial"))
    queue = RecordingGraphQueue()

    result = sync(library, queue, position=0.5)

    assert queue.enqueued == ["book-1"]
    assert result.graph_generation_queued is True


def test_rewinding_does_not_queue_graph_generation() -> None:
    library = FakeLibraryRepository(reading_state(0.9))
    queue = RecordingGraphQueue()

    result = sync(library, queue, position=0.3)

    assert queue.enqueued == []
    assert result.graph_generation_queued is False
    assert library.updates == [("book-1", 0.3)]


def test_an_unchanged_position_does_not_queue_graph_generation() -> None:
    library = FakeLibraryRepository(reading_state(0.5))
    queue = RecordingGraphQueue()

    result = sync(library, queue, position=0.5)

    assert queue.enqueued == []
    assert result.graph_generation_queued is False


def test_a_book_still_processing_does_not_queue_graph_generation() -> None:
    library = FakeLibraryRepository(reading_state(0.1, processing_status="processing"))
    queue = RecordingGraphQueue()

    result = sync(library, queue, position=0.9)

    assert queue.enqueued == []
    assert result.graph_generation_queued is False


def test_a_failed_book_does_not_queue_graph_generation() -> None:
    library = FakeLibraryRepository(reading_state(0.1, processing_status="failed"))
    queue = RecordingGraphQueue()

    sync(library, queue, position=0.9)

    assert queue.enqueued == []


def test_the_response_reports_the_current_graph_revision() -> None:
    library = FakeLibraryRepository(reading_state(0.1, graph_revision=11))

    result = sync(library, RecordingGraphQueue(), position=0.9)

    assert result.graph_revision == 11
    assert result.book_id == "book-1"
    assert result.position == 0.9


def test_a_queue_failure_does_not_fail_the_sync() -> None:
    library = FakeLibraryRepository(reading_state(0.1))

    result = sync(library, FailingGraphQueue(), position=0.9)

    assert result.graph_generation_queued is False
    assert library.updates == [("book-1", 0.9)]


def test_an_unknown_document_is_rejected_before_storing_progress() -> None:
    library = FakeLibraryRepository(reading_state(0.1))

    with pytest.raises(DomainBookNotFoundError):
        sync(library, RecordingGraphQueue(), document_hash="unknown")

    assert library.updates == []


def test_a_book_the_caller_does_not_own_is_rejected() -> None:
    library = FakeLibraryRepository(None)

    with pytest.raises(DomainBookNotFoundError):
        sync(library, RecordingGraphQueue())

    assert library.updates == []


def test_progress_is_stored_when_no_queue_is_configured() -> None:
    library = FakeLibraryRepository(reading_state(0.1))

    result = sync(library, None, position=0.9)

    assert result.graph_generation_queued is False
    assert library.updates == [("book-1", 0.9)]
