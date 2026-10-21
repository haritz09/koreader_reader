"""Library membership: the books one owner keeps, and whether they deleted them."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class UserBookRecord(Base):
	__tablename__ = "user_books"
	__table_args__ = (
		Index("ix_user_books_owner_deleted", "owner_id", "deleted_at"),
		CheckConstraint(
			"progress_position >= 0.0 AND progress_position <= 1.0",
			name="ck_user_books_progress_position",
		),
	)

	owner_id: Mapped[str] = mapped_column(
		ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
	)
	book_id: Mapped[str] = mapped_column(
		ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
	)
	added_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	progress_position: Mapped[float] = mapped_column(
		Float, nullable=False, server_default="0.0"
	)
	last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
