"""Errors raised by embedding providers and the RAG pipeline."""


class EmbeddingError(Exception):
    pass


class EmbeddingConfigurationError(EmbeddingError):
    pass


class EmbeddingPermanentError(EmbeddingError):
    pass


class EmbeddingTransientError(EmbeddingError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EmbeddingQuotaExhaustedError(EmbeddingError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class RagBuildDeferred(Exception):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("RAG build deferred")
        self.retry_after = retry_after


class RagIndexNotReadyError(Exception):
    """Raised when chat cannot read the index at its current state."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"RAG index is not ready: {reason}")
        self.reason = reason
