"""Library membership: the books one owner keeps, and whether they deleted them.

Book content is shared across owners, so ownership and deletion live here rather
than on ``books``. ``deleted_at`` is a full soft-delete: neither the book row nor
its derived content is touched until a future purge runs.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class UserBookRecord(Base):
	__tablename__ = "user_books"
	__table_args__ = (Index("ix_user_books_owner_deleted", "owner_id", "deleted_at"),)

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
