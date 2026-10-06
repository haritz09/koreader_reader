"""Knowledge graph endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_book_graph_use_case
from api.schemas.graph import GraphEdgeResponse, GraphNodeResponse, GraphResponse
from core.application.use_cases.get_book_graph import GetBookGraphUseCase
from core.domain.errors import BookNotFoundError, BookNotReadyError

router = APIRouter(prefix="/ebooks", tags=["graph"])


@router.get(
	"/{book_id}/graph",
	response_model=GraphResponse,
)
async def get_book_graph(
	book_id: str,
	use_case: GetBookGraphUseCase = Depends(get_book_graph_use_case),
) -> GraphResponse:
	try:
		graph = await use_case.execute(book_id)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
		) from error
	except BookNotReadyError as error:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT, detail=str(error)
		) from error

	return GraphResponse(
		book_id=graph.book_id,
		position=graph.position,
		revision=graph.revision,
		nodes=[
			GraphNodeResponse(
				node_id=node.node_id,
				label=node.label,
				node_type=node.node_type,
				first_seen_position=node.first_seen_position,
				mention_count=node.mention_count,
				description=node.description,
				sub_type=node.sub_type,
				aliases=list(node.aliases),
			)
			for node in graph.nodes
		],
		edges=[
			GraphEdgeResponse(
				edge_id=edge.edge_id,
				source_id=edge.source_id,
				target_id=edge.target_id,
				statement=edge.statement,
				position=edge.position,
				chunk_id=edge.chunk_id,
			)
			for edge in graph.edges
		],
	)
