"""Canonical book processing statuses."""

PENDING = "pending"
PROCESSING = "processing"
READY = "ready"
PARTIAL = "partial"
FAILED = "failed"

TERMINAL_STATUSES: frozenset[str] = frozenset({READY, PARTIAL, FAILED})

GRAPH_STATUSES: frozenset[str] = frozenset({READY, PARTIAL})

RETRYABLE_STATUSES: frozenset[str] = frozenset({FAILED, PARTIAL})
