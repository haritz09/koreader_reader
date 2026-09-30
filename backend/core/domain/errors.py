"""Domain errors shared across use cases."""


class BookNotFoundError(Exception):
    """Raised when a book identifier does not resolve to a stored book."""


class BookNotReadyError(Exception):
    """Raised when a book has not finished processing and cannot be read yet."""

    def __init__(self, processing_status: str) -> None:
        super().__init__(f"Book is not ready: {processing_status}")
        self.processing_status = processing_status
