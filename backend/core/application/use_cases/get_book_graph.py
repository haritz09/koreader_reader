"""Use case for reading the anti-spoiler graph."""

from core.domain.entities.graph import BookGraph
from core.domain.errors import BookNotFoundError, BookNotReadyError
from core.ports.library_repository import LibraryRepository
from core.services.graph_assembly import GraphAssemblyService

READY_STATUS = "ready"


class GetBookGraphUseCase:
    """Return the graph a reader has earned at their stored progress position."""

    def __init__(
        self,
        library: LibraryRepository,
        assembly: GraphAssemblyService,
    ) -> None:
        self._library = library
        self._assembly = assembly

    async def execute(self, owner_id: str, book_id: str) -> BookGraph:
        state = await self._library.get_reading_state(owner_id, book_id)
        if state is None:
            raise BookNotFoundError(book_id)
        if state.processing_status != READY_STATUS:
            raise BookNotReadyError(state.processing_status)
        return await self._assembly.build(book_id, state.progress_position)
