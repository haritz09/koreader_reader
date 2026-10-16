from typing import Protocol

from core.domain.entities.user import User


class UserRepository(Protocol):
    async def create_anonymous(self) -> User:
        ...

    async def get_by_id(self, user_id: str) -> User | None:
        ...
