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
	get_token_service,
	get_user_repository,
)
from api.schemas.session import SessionCreatedResponse, SessionResponse
from core.application.use_cases.create_session import CreateAnonymousSessionUseCase
from core.config import settings
from core.ports.token_service import TokenService
from core.ports.user_repository import UserRepository

router = APIRouter(prefix="/session", tags=["session"])

SECONDS_PER_DAY = 24 * 60 * 60


@router.get("", response_model=SessionResponse)
async def read_session(
	owner_id: str = Depends(get_current_owner),
	users: UserRepository = Depends(get_user_repository),
) -> SessionResponse:
	user = await users.get_by_id(owner_id)
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown session"
		)
	return SessionResponse(user_id=user.id, is_anonymous=user.is_anonymous)


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
	response.set_cookie(
		key=settings.session_cookie_name,
		value=token,
		httponly=True,
		secure=settings.session_cookie_secure,
		samesite=settings.session_cookie_samesite,
		max_age=settings.jwt_ttl_days * SECONDS_PER_DAY,
		path="/",
	)
	return SessionCreatedResponse(
		user_id=user.id, is_anonymous=user.is_anonymous, token=token
	)
