"""Book persistence model."""

from sqlalchemy import CheckConstraint, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Book(Base):
	__tablename__ = "books"
	__table_args__ = (
		CheckConstraint(
			"progress_position >= 0.0 AND progress_position <= 1.0",
			name="ck_books_progress_position",
		),
	)

	id: Mapped[str] = mapped_column(String(255), primary_key=True)
	document_hash: Mapped[str] = mapped_column(
		String(64), unique=True, index=True, nullable=False
	)
	storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
	processing_status: Mapped[str] = mapped_column(
		String(32), nullable=False, default="pending"
	)
	processing_error: Mapped[str | None] = mapped_column(String(2000))
	progress_position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
	graph_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
