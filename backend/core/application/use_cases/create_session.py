"""Use case for starting an anonymous session."""

from core.domain.entities.user import User
from core.ports.user_repository import UserRepository


class CreateAnonymousSessionUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self) -> User:
        return await self._users.create_anonymous()
