"""User persistence model.

Users start anonymous so the app works without a login. Claiming a user later
only attaches credentials to the existing row, so no library data is migrated.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class UserRecord(Base):
	__tablename__ = "users"

	id: Mapped[str] = mapped_column(String(255), primary_key=True)
	is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
