"""Session request and response schemas."""

from pydantic import BaseModel


class SessionResponse(BaseModel):
    user_id: str
    is_anonymous: bool


class SessionCreatedResponse(SessionResponse):
    """The token is returned so a device without a browser can store it."""

    token: str
