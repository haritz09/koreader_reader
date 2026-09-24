"""Book persistence model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Book(Base):
	__tablename__ = "books"

	id: Mapped[str] = mapped_column(String(255), primary_key=True)
	document_hash: Mapped[str] = mapped_column(
		String(64), unique=True, index=True, nullable=False
	)
