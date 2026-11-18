"""Use case for reading the session behind a verified token."""

from core.domain.entities.user import User
from core.domain.errors import SessionNotFoundError
from core.ports.user_repository import UserRepository


class ReadSessionUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, owner_id: str) -> User:
        user = await self._users.get_by_id(owner_id)
        if user is None:
            raise SessionNotFoundError(owner_id)
        return user
