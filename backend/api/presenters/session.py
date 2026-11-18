"""Presenters for the session API."""

from fastapi import Response

from api.schemas.session import SessionCreatedResponse, SessionResponse
from core.config import settings
from core.domain.entities.user import User

SECONDS_PER_DAY = 24 * 60 * 60


def session_response(user: User) -> SessionResponse:
    return SessionResponse(user_id=user.id, is_anonymous=user.is_anonymous)


def created_session_response(
    response: Response,
    user: User,
    token: str,
) -> SessionCreatedResponse:
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
        user_id=user.id,
        is_anonymous=user.is_anonymous,
        token=token,
    )
