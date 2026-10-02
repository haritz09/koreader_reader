"""Use case for synchronizing normalized reading progress."""

import logging
from dataclasses import dataclass

from core.domain.entities.graph import BookGraphState
from core.domain.errors import BookNotFoundError
from core.ports.job_queue import GraphGenerationQueue
from core.ports.reading_progress_provider import ReadingProgressProvider
from core.ports.reading_progress_store import ReadingProgressStore

logger = logging.getLogger(__name__)

READY_STATUS = "ready"


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a sync, including what the client needs to refresh the graph."""

    book_id: str
    position: float
    graph_revision: int
    graph_generation_queued: bool


class SyncProgressUseCase:
    def __init__(
        self,
        provider: ReadingProgressProvider,
        progress_store: ReadingProgressStore,
        graph_queue: GraphGenerationQueue | None = None,
    ) -> None:
        self._provider = provider
        self._progress_store = progress_store
        self._graph_queue = graph_queue

    async def execute(self, document_hash: str, position: float) -> SyncResult:
        progress = await self._provider.resolve_progress(document_hash, position)
        if progress is None:
            raise BookNotFoundError(document_hash)

        state = await self._progress_store.get_graph_state(progress.book_id)
        await self._progress_store.update_progress(progress.book_id, position)
        queued = await self._queue_when_advanced(progress.book_id, position, state)
        return SyncResult(
            book_id=progress.book_id,
            position=position,
            graph_revision=state.graph_revision if state else 0,
            graph_generation_queued=queued,
        )

    async def _queue_when_advanced(
        self,
        book_id: str,
        position: float,
        state: BookGraphState | None,
    ) -> bool:
        """Queue graph generation only when the reader moved forward.

        A rewind deliberately queues nothing. The graph read filters by the
        stored position on every request, so re-reading already yields a smaller
        graph and the job is only a refresh of entity identity, never a gate on
        what the reader can see.
        """
        if self._graph_queue is None or state is None:
            return False
        if state.processing_status != READY_STATUS:
            return False
        if position <= state.progress_position:
            return False
        try:
            await self._graph_queue.enqueue(book_id)
        except Exception:
            logger.exception("Could not queue graph generation for book %s", book_id)
            return False
        return True
