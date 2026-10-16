from typing import Protocol


class TokenService(Protocol):
    """Issues and verifies the bearer token that carries the owner identity."""

    def issue(self, user_id: str) -> str:
        ...

    def verify(self, token: str) -> str | None:
        ...
