import asyncio

import pytest

from core.application.use_cases.sync_progress import (
    BookNotFoundError,
    SyncProgressUseCase,
)
from core.domain.entities.graph import BookGraphState
from core.domain.entities.reading_progress import ReadingProgress
from core.domain.errors import BookNotFoundError as DomainBookNotFoundError


class StubProgressProvider:
    def __init__(self, known_hash: str = "document-hash") -> None:
        self._known_hash = known_hash

    async def resolve_progress(
        self, document_hash: str, position: float
    ) -> ReadingProgress | None:
        if document_hash != self._known_hash:
            return None
        return ReadingProgress(book_id="book-1", position=position)


class StubProgressStore:
    def __init__(
        self,
        state: BookGraphState | None = None,
    ) -> None:
        self.state = state
        self.updates: list[tuple[str, float]] = []

    async def update_progress(self, book_id: str, position: float) -> None:
        self.updates.append((book_id, position))

    async def get_graph_state(self, book_id: str) -> BookGraphState | None:
        return self.state


class RecordingGraphQueue:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, book_id: str) -> None:
        self.enqueued.append(book_id)


class FailingGraphQueue:
    async def enqueue(self, book_id: str) -> None:
        raise RuntimeError("redis unavailable")


def state(
    progress_position: float,
    processing_status: str = "ready",
    graph_revision: int = 3,
) -> BookGraphState:
    return BookGraphState(
        book_id="book-1",
        progress_position=progress_position,
        processing_status=processing_status,
        graph_revision=graph_revision,
    )


def sync(
    store: StubProgressStore,
    queue=None,
    position: float = 0.5,
    document_hash: str = "document-hash",
):
    use_case = SyncProgressUseCase(StubProgressProvider(), store, queue)
    return asyncio.run(use_case.execute(document_hash, position))


def test_moving_forward_queues_graph_generation() -> None:
    store = StubProgressStore(state(0.2))
    queue = RecordingGraphQueue()

    result = sync(store, queue, position=0.5)

    assert queue.enqueued == ["book-1"]
    assert result.graph_generation_queued is True
    assert store.updates == [("book-1", 0.5)]


def test_rewinding_does_not_queue_graph_generation() -> None:
    store = StubProgressStore(state(0.9))
    queue = RecordingGraphQueue()

    result = sync(store, queue, position=0.3)

    assert queue.enqueued == []
    assert result.graph_generation_queued is False
    assert store.updates == [("book-1", 0.3)]


def test_an_unchanged_position_does_not_queue_graph_generation() -> None:
    store = StubProgressStore(state(0.5))
    queue = RecordingGraphQueue()

    result = sync(store, queue, position=0.5)

    assert queue.enqueued == []
    assert result.graph_generation_queued is False


def test_a_book_still_processing_does_not_queue_graph_generation() -> None:
    store = StubProgressStore(state(0.1, processing_status="processing"))
    queue = RecordingGraphQueue()

    result = sync(store, queue, position=0.9)

    assert queue.enqueued == []
    assert result.graph_generation_queued is False


def test_a_failed_book_does_not_queue_graph_generation() -> None:
    store = StubProgressStore(state(0.1, processing_status="failed"))
    queue = RecordingGraphQueue()

    sync(store, queue, position=0.9)

    assert queue.enqueued == []


def test_the_response_reports_the_current_graph_revision() -> None:
    store = StubProgressStore(state(0.1, graph_revision=11))

    result = sync(store, RecordingGraphQueue(), position=0.9)

    assert result.graph_revision == 11
    assert result.book_id == "book-1"
    assert result.position == 0.9


def test_a_queue_failure_does_not_fail_the_sync() -> None:
    store = StubProgressStore(state(0.1))

    result = sync(store, FailingGraphQueue(), position=0.9)

    assert result.graph_generation_queued is False
    assert store.updates == [("book-1", 0.9)]


def test_an_unknown_document_is_rejected_before_storing_progress() -> None:
    store = StubProgressStore(state(0.1))

    with pytest.raises(DomainBookNotFoundError):
        sync(store, RecordingGraphQueue(), document_hash="unknown")

    assert store.updates == []


def test_progress_is_stored_when_no_queue_is_configured() -> None:
    store = StubProgressStore(state(0.1))

    result = sync(store, None, position=0.9)

    assert result.graph_generation_queued is False
    assert store.updates == [("book-1", 0.9)]


def test_the_use_case_still_exports_its_not_found_error() -> None:
    assert BookNotFoundError is DomainBookNotFoundError
