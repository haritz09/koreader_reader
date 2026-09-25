"""Chapter and chunk persistence models."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ChapterRecord(Base):
	__tablename__ = "chapters"

	id: Mapped[str] = mapped_column(String(255), primary_key=True)
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	title: Mapped[str] = mapped_column(String(500), nullable=False)
	chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)


class ChunkRecord(Base):
	__tablename__ = "chunks"
	__table_args__ = (UniqueConstraint("book_id", "chunk_index"),)

	id: Mapped[str] = mapped_column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), nullable=False)
	chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
	text: Mapped[str] = mapped_column(Text, nullable=False)
	start_pctg: Mapped[float] = mapped_column(Float, nullable=False)
	end_pctg: Mapped[float] = mapped_column(Float, nullable=False)
