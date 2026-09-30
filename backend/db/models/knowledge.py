"""Chapter, chunk and knowledge persistence models."""

import uuid

from sqlalchemy import (
	CheckConstraint,
	Float,
	ForeignKey,
	Index,
	Integer,
	String,
	Text,
	UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

READING_POSITION_CHECK = "reading_position >= 0.0 AND reading_position <= 1.0"


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


class EntityRecord(Base):
	__tablename__ = "entities"
	__table_args__ = (
		Index("ix_entities_book_reading_position", "book_id", "reading_position"),
		Index("ix_entities_book_canonical_id", "book_id", "canonical_id"),
		CheckConstraint(READING_POSITION_CHECK, name="ck_entities_reading_position"),
	)

	id: Mapped[str] = mapped_column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), nullable=False)
	name: Mapped[str] = mapped_column(String(500), nullable=False)
	entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
	reading_position: Mapped[float] = mapped_column(Float, nullable=False)
	canonical_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"))
	resolution_method: Mapped[str | None] = mapped_column(String(32))


class FactRecord(Base):
	__tablename__ = "facts"
	__table_args__ = (
		Index("ix_facts_book_reading_position", "book_id", "reading_position"),
		CheckConstraint(READING_POSITION_CHECK, name="ck_facts_reading_position"),
	)

	id: Mapped[str] = mapped_column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), nullable=False)
	statement: Mapped[str] = mapped_column(Text, nullable=False)
	subject: Mapped[str | None] = mapped_column(String(500))
	object: Mapped[str | None] = mapped_column(String(500))
	reading_position: Mapped[float] = mapped_column(Float, nullable=False)


class EventRecord(Base):
	__tablename__ = "events"
	__table_args__ = (
		Index("ix_events_book_reading_position", "book_id", "reading_position"),
		CheckConstraint(READING_POSITION_CHECK, name="ck_events_reading_position"),
	)

	id: Mapped[str] = mapped_column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), nullable=False)
	description: Mapped[str] = mapped_column(Text, nullable=False)
	reading_position: Mapped[float] = mapped_column(Float, nullable=False)


class LocationRecord(Base):
	__tablename__ = "locations"
	__table_args__ = (
		Index("ix_locations_book_reading_position", "book_id", "reading_position"),
		CheckConstraint(READING_POSITION_CHECK, name="ck_locations_reading_position"),
	)

	id: Mapped[str] = mapped_column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), nullable=False)
	name: Mapped[str] = mapped_column(String(500), nullable=False)
	description: Mapped[str | None] = mapped_column(Text)
	reading_position: Mapped[float] = mapped_column(Float, nullable=False)
