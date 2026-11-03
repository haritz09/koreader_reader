"""SQLAlchemy models for the RAG index."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from rag.domain.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_SOURCE_TYPE_VALUES
from rag.domain.status import RAG_INDEX_STATUS_VALUES

READING_POSITION_CHECK = "reading_position >= 0.0 AND reading_position <= 1.0"
FIRST_SEEN_POSITION_CHECK = (
    "first_seen_position >= 0.0 AND first_seen_position <= 1.0"
)
EMBEDDING_SOURCE_TYPE_CHECK = f"source_type IN ({EMBEDDING_SOURCE_TYPE_VALUES})"
RAG_INDEX_STATUS_CHECK = f"status IN ({RAG_INDEX_STATUS_VALUES})"


class RagEmbeddingRecord(Base):
    __tablename__ = "rag_embeddings"
    __table_args__ = (
        UniqueConstraint("book_id", "source_type", "source_id", "model"),
        Index("ix_rag_embeddings_book_source_position", "book_id", "source_type", "reading_position"),
        Index("ix_rag_embeddings_book_model", "book_id", "model"),
        CheckConstraint(READING_POSITION_CHECK, name="ck_rag_embeddings_reading_position"),
        CheckConstraint(EMBEDDING_SOURCE_TYPE_CHECK, name="ck_rag_embeddings_source_type"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True
    )
    reading_position: Mapped[float] = mapped_column(Float, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RagCommunityRunRecord(Base):
    __tablename__ = "rag_community_runs"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    graph_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    modularity: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RagCommunityRecord(Base):
    __tablename__ = "rag_communities"
    __table_args__ = (
        Index("ix_rag_communities_run_level", "run_id", "level"),
        Index("ix_rag_communities_book_level", "book_id", "level"),
        CheckConstraint(
            FIRST_SEEN_POSITION_CHECK,
            name="ck_rag_communities_first_seen_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("rag_community_runs.id", ondelete="CASCADE"), nullable=False
    )
    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("rag_communities.id", ondelete="CASCADE"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    seed_node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_position: Mapped[float] = mapped_column(Float, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    internal_weight: Mapped[float] = mapped_column(Float, nullable=False)


class RagCommunityMemberRecord(Base):
    __tablename__ = "rag_community_members"
    __table_args__ = (
        Index("ix_rag_community_members_node", "node_id"),
        Index(
            "ix_rag_community_members_position",
            "community_id",
            "first_seen_position",
        ),
    )

    community_id: Mapped[str] = mapped_column(
        ForeignKey("rag_communities.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    first_seen_position: Mapped[float] = mapped_column(Float, nullable=False)


class RagIndexStateRecord(Base):
    __tablename__ = "rag_index_states"
    __table_args__ = (
        CheckConstraint(RAG_INDEX_STATUS_CHECK, name="ck_rag_index_states_status"),
    )

    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
    )
    rag_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    graph_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("rag_community_runs.id", ondelete="SET NULL"), nullable=True
    )
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
