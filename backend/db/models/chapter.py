"""Chapter persistence model."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ChapterRecord(Base):
	__tablename__ = "chapters"

	id: Mapped[str] = mapped_column(String(255), primary_key=True)
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	title: Mapped[str] = mapped_column(String(500), nullable=False)
	chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
