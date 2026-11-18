"""Anonymous session endpoints.

The app works without a login: the first POST creates an anonymous owner and
sets the bearer token as an httpOnly cookie. The same token can be configured on
a device (for example KOReader) and sent as ``Authorization: Bearer``.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.dependencies import (
    enforce_session_rate_limit,
    get_create_session_use_case,
    get_current_owner,
    get_read_session_use_case,
    get_token_service,
)
from api.presenters.session import created_session_response, session_response
from api.schemas.session import SessionCreatedResponse, SessionResponse
from core.application.use_cases.create_session import CreateAnonymousSessionUseCase
from core.application.use_cases.read_session import ReadSessionUseCase
from core.domain.errors import SessionNotFoundError
from core.ports.token_service import TokenService

router = APIRouter(prefix="/session", tags=["session"])


@router.get("", response_model=SessionResponse)
async def read_session(
    owner_id: str = Depends(get_current_owner),
    use_case: ReadSessionUseCase = Depends(get_read_session_use_case),
) -> SessionResponse:
    try:
        user = await use_case.execute(owner_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown session"
        ) from error
    return session_response(user)


@router.post(
    "",
    response_model=SessionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_session_rate_limit)],
)
async def create_session(
    response: Response,
    use_case: CreateAnonymousSessionUseCase = Depends(get_create_session_use_case),
    tokens: TokenService = Depends(get_token_service),
) -> SessionCreatedResponse:
    user = await use_case.execute()
    token = tokens.issue(user.id)
    return created_session_response(response, user, token)
