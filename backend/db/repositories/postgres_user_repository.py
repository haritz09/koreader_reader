"""User repository implementation for postgres."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.user import User
from db.models.user import UserRecord


class PostgresUserRepository:
	def __init__(self, session: AsyncSession) -> None:
		self._session = session

	async def create_anonymous(self) -> User:
		record = UserRecord(id=str(uuid.uuid4()), is_anonymous=True)
		self._session.add(record)
		await self._session.commit()
		await self._session.refresh(record)
		return User(id=record.id, is_anonymous=record.is_anonymous)

	async def get_by_id(self, user_id: str) -> User | None:
		result = await self._session.execute(
			select(UserRecord).where(UserRecord.id == user_id)
		)
		record = result.scalar_one_or_none()
		if record is None:
			return None
		return User(id=record.id, is_anonymous=record.is_anonymous)
