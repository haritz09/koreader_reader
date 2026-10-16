"""JWT-backed session tokens for anonymous owners."""

from datetime import UTC, datetime, timedelta

import jwt


class JwtTokenService:
    """Signs an opaque owner reference into a verifiable bearer token.

    The owner id never comes from the client: it is derived from the signed
    ``sub`` claim, so a caller cannot address another owner's library.
    """

    def __init__(
        self, secret: str, algorithm: str = "HS256", ttl_days: int = 365
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._ttl = timedelta(days=ttl_days)

    def issue(self, user_id: str) -> str:
        now = datetime.now(UTC)
        payload = {"sub": user_id, "iat": now, "exp": now + self._ttl}
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify(self, token: str) -> str | None:
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=[self._algorithm]
            )
        except jwt.PyJWTError:
            return None
        subject = payload.get("sub")
        return subject if isinstance(subject, str) and subject else None
