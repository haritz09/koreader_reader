"""Reading progress endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_sync_progress_use_case
from api.schemas.progress import KoreaderSyncRequest, KoreaderSyncResponse
from core.application.use_cases.sync_progress import SyncProgressUseCase
from core.domain.errors import BookNotFoundError

router = APIRouter(prefix="/adapters/koreader", tags=["koreader"])


@router.post(
	"/sync",
	response_model=KoreaderSyncResponse,
	status_code=status.HTTP_202_ACCEPTED,
)
async def sync_koreader_progress(
	payload: KoreaderSyncRequest,
	use_case: SyncProgressUseCase = Depends(get_sync_progress_use_case),
) -> KoreaderSyncResponse:
	try:
		result = await use_case.execute(payload.document, payload.progress)
	except BookNotFoundError as error:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="KOReader document is not mapped to a book",
		) from error

	return KoreaderSyncResponse(
		book_id=result.book_id,
		position=result.position,
		device=payload.device,
		graph_revision=result.graph_revision,
		graph_generation_queued=result.graph_generation_queued,
	)
