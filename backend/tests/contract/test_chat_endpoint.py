"""Chat endpoint contract: HTTP shapes, ownership, and index gating."""

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    get_answer_provider,
    get_embedding_provider,
    get_library_repository,
    get_rag_index_reader,
    get_retrieval_repository,
    get_strategy_classifier,
)
from main import app
from rag.domain.chat import AnswerDraft
from rag.domain.index_state import RagIndexState
from rag.domain.retrieval import RetrievalStrategy, RetrievedChunk
from rag.domain.status import RagIndexStatus
from tests.fixtures.embeddings import FakeEmbeddingProvider
from tests.fixtures.repositories import FakeLibraryRepository, reading_state

MODEL = "test-model"


def known_library(
    progress_position: float = 0.5,
    processing_status: str = "ready",
) -> FakeLibraryRepository:
    return FakeLibraryRepository(
        reading_state(progress_position, processing_status),
        known_book_ids={"book-123"},
    )


class StubIndexReader:
    def __init__(self, state: RagIndexState | None = None) -> None:
        self.state = state or RagIndexState(RagIndexStatus.READY, MODEL)

    async def get_index_state(self, book_id: str) -> RagIndexState | None:
        return self.state


class FilteringRetrievalRepository:
    """Applies the same position filter the SQL implementation applies."""

    def __init__(self) -> None:
        self.chunks = [
            RetrievedChunk("early", 0, 0.1, 0.1, "Early text."),
            RetrievedChunk("boundary", 1, 0.5, 0.2, "Boundary text."),
            RetrievedChunk("late", 2, 0.9, 0.05, "Late text."),
        ]
        self.positions: list[float] = []

    async def search_chunks(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        self.positions.append(position)
        return [item for item in self.chunks if item.reading_position <= position]


class CitingAnswerProvider:
    def __init__(self) -> None:
        self.questions: list[str] = []

    async def answer(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
    ) -> AnswerDraft:
        self.questions.append(question)
        return AnswerDraft(
            text="Only what the visible text says.",
            cited_chunk_ids=tuple(item.chunk_id for item in chunks),
        )


class RagStrategyClassifier:
    async def classify_strategy(self, question: str) -> RetrievalStrategy:
        return RetrievalStrategy.RAG


def post_chat(
    *,
    body: dict | None = None,
    path: str = "/api/v1/ebooks/book-123/chat",
    library: FakeLibraryRepository | None = None,
    index: StubIndexReader | None = None,
    retrieval: FilteringRetrievalRepository | None = None,
) -> tuple[object, FilteringRetrievalRepository]:
    retrieval = retrieval or FilteringRetrievalRepository()
    overrides = {
        get_library_repository: lambda: library or known_library(),
        get_rag_index_reader: lambda: index or StubIndexReader(),
        get_retrieval_repository: lambda: retrieval,
        get_embedding_provider: lambda: FakeEmbeddingProvider(),
        get_answer_provider: lambda: CitingAnswerProvider(),
        get_strategy_classifier: lambda: RagStrategyClassifier(),
    }
    for dependency, override in overrides.items():
        app.dependency_overrides[dependency] = override
    try:
        response = TestClient(app).post(
            path, json={"question": "who appears"} if body is None else body
        )
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
    return response, retrieval


def test_chat_returns_an_answer_with_typed_sources() -> None:
    response, retrieval = post_chat()

    assert response.status_code == 200
    body = response.json()
    assert body["book_id"] == "book-123"
    assert body["position"] == 0.5
    assert isinstance(body["answer"], str) and body["answer"]
    assert [source["chunk_id"] for source in body["sources"]] == ["early", "boundary"]
    for source in body["sources"]:
        assert isinstance(source["chunk_id"], str)
        assert isinstance(source["chunk_index"], int)
        assert isinstance(source["reading_position"], float)
        assert source["reading_position"] <= 0.5
    assert retrieval.positions == [0.5]


def test_chat_returns_not_found_for_an_unknown_book() -> None:
    response, _ = post_chat(path="/api/v1/ebooks/missing/chat")

    assert response.status_code == 404


def test_chat_conflicts_while_the_book_is_processing() -> None:
    response, _ = post_chat(library=known_library(processing_status="processing"))

    assert response.status_code == 409


def test_chat_conflicts_when_the_index_is_not_ready() -> None:
    response, _ = post_chat(index=StubIndexReader(RagIndexState(RagIndexStatus.FAILED, MODEL)))

    assert response.status_code == 409
    assert "index" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": "   "},
        {"question": "x" * 2001},
        {"question": 42},
    ],
)
def test_chat_rejects_an_invalid_question(body: dict) -> None:
    response, _ = post_chat(body=body)

    assert response.status_code == 422
