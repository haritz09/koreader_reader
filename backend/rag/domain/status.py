"""Canonical status values for a book's RAG index."""

from enum import StrEnum


class RagIndexStatus(StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


RAG_INDEX_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in RagIndexStatus)

RAG_INDEX_CURRENT_STATUSES: frozenset[RagIndexStatus] = frozenset(
    {RagIndexStatus.READY, RagIndexStatus.PARTIAL}
)
