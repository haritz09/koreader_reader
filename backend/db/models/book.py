"""Book persistence model."""

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Book(Base):
	__tablename__ = "books"

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
