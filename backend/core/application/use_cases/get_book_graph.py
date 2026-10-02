"""Use case for reading the anti-spoiler graph."""

from core.domain.entities.graph import BookGraph
from core.domain.errors import BookNotFoundError, BookNotReadyError
from core.ports.book_repository import BookRepository
from core.services.graph_assembly import GraphAssemblyService

READY_STATUS = "ready"


class GetBookGraphUseCase:
    """Return the graph a reader has earned at their stored progress position."""

    def __init__(
        self,
        book_repository: BookRepository,
        assembly: GraphAssemblyService,
    ) -> None:
        self._book_repository = book_repository
        self._assembly = assembly

    async def execute(self, book_id: str) -> BookGraph:
        state = await self._book_repository.get_graph_state(book_id)
        if state is None:
            raise BookNotFoundError(book_id)
        if state.processing_status != READY_STATUS:
            raise BookNotReadyError(state.processing_status)
        return await self._assembly.build(book_id, state.progress_position)
