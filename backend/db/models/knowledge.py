"""Knowledge persistence models."""

import uuid

from sqlalchemy import (
	ARRAY,
	CheckConstraint,
	Float,
	ForeignKey,
	Index,
	Integer,
	String,
	Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

READING_POSITION_CHECK = "reading_position >= 0.0 AND reading_position <= 1.0"

ENTITY_TYPE_VALUES = "'character', 'enemy', 'artifact', 'organization', 'concept', 'other'"
ENTITY_TYPE_CHECK = f"entity_type IN ({ENTITY_TYPE_VALUES})"

IMPORTANCE_VALUES = "1, 2, 3"
IMPORTANCE_CHECK = f"importance IS NULL OR importance IN ({IMPORTANCE_VALUES})"


class EntityRecord(Base):
	__tablename__ = "entities"
	__table_args__ = (
		Index("ix_entities_book_reading_position", "book_id", "reading_position"),
		Index("ix_entities_book_canonical_id", "book_id", "canonical_id"),
		CheckConstraint(READING_POSITION_CHECK, name="ck_entities_reading_position"),
		CheckConstraint(ENTITY_TYPE_CHECK, name="ck_entities_entity_type"),
		CheckConstraint(IMPORTANCE_CHECK, name="ck_entities_importance"),
	)

	id: Mapped[str] = mapped_column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
	book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), nullable=False)
	chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), nullable=False)
	name: Mapped[str] = mapped_column(String(500), nullable=False)
	entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
	sub_type: Mapped[str | None] = mapped_column(String(100))
	aliases: Mapped[list[str]] = mapped_column(
		ARRAY(String(500)), nullable=False, default=list, server_default="{}"
	)
	reading_position: Mapped[float] = mapped_column(Float, nullable=False)
	canonical_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"))
	resolution_method: Mapped[str | None] = mapped_column(String(32))
	importance: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
	name: Mapped[str] = mapped_column(
		String(500), nullable=False, default="", server_default=""
	)
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
