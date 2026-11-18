"""Knowledge graph endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_book_graph_use_case, get_current_owner
from api.presenters.graph import graph_response
from api.schemas.graph import GraphResponse
from core.application.use_cases.get_book_graph import GetBookGraphUseCase
from core.domain.errors import BookNotFoundError, BookNotReadyError

router = APIRouter(prefix="/ebooks", tags=["graph"])


@router.get(
	"/{book_id}/graph",
	response_model=GraphResponse,
)
async def get_book_graph(
	book_id: str,
	owner_id: str = Depends(get_current_owner),
	use_case: GetBookGraphUseCase = Depends(get_book_graph_use_case),
) -> GraphResponse:
	try:
		graph = await use_case.execute(owner_id, book_id)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
		) from error
	except BookNotReadyError as error:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT, detail=str(error)
		) from error

	return graph_response(graph)
