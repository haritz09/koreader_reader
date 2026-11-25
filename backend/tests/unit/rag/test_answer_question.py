"""Chat answers: spoiler filtering, citation traceability, and index gating."""

import asyncio
from collections.abc import Sequence

import pytest

from core.domain.errors import BookNotFoundError, BookNotReadyError
from rag.application.answer_question import AnswerQuestionUseCase
from rag.application.retrieve import RetrieveContextUseCase
from rag.domain.chat import AnswerDraft
from rag.domain.errors import RagIndexNotReadyError
from rag.domain.index_state import RagIndexState
from rag.domain.retrieval import RetrievalResult, RetrievalStrategy, RetrievedChunk
from rag.domain.status import RagIndexStatus
from tests.fixtures.embeddings import FakeEmbeddingProvider
from tests.fixtures.repositories import FakeLibraryRepository, reading_state

MODEL = "test-model"


def chunk(
    chunk_id: str,
    reading_position: float,
    chunk_index: int = 0,
    distance: float = 0.1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        reading_position=reading_position,
        distance=distance,
        text=f"text-{chunk_id}",
    )


class _FakeIndexReader:
    def __init__(self, state: RagIndexState | None) -> None:
        self.state = state

    async def get_index_state(self, book_id: str) -> RagIndexState | None:
        return self.state


class _FakeRetrievalRepository:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[str, float, str, list[float], int]] = []

    async def search_chunks(
        self,
        book_id: str,
        position: float,
        model: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        self.calls.append((book_id, position, model, list(query_embedding), limit))
        return [item for item in self.chunks if item.reading_position <= position]


class _FakeAnswerProvider:
    def __init__(self, cited_chunk_ids: Sequence[str]) -> None:
        self.cited_chunk_ids = tuple(cited_chunk_ids)
        self.calls: list[tuple[str, list[str]]] = []

    async def answer(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
    ) -> AnswerDraft:
        self.calls.append((question, [item.chunk_id for item in chunks]))
        return AnswerDraft(text="Because.", cited_chunk_ids=self.cited_chunk_ids)


class _FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[str, float, str]] = []

    async def execute(
        self,
        book_id: str,
        position: float,
        question: str,
    ) -> RetrievalResult:
        self.calls.append((book_id, position, question))
        return RetrievalResult(
            book_id=book_id,
            position=position,
            model=MODEL,
            chunks=tuple(item for item in self.chunks if item.reading_position <= position),
        )


class _FakeClassifier:
    def __init__(self, strategy: RetrievalStrategy) -> None:
        self.strategy = strategy
        self.calls: list[str] = []

    async def classify_strategy(self, question: str) -> RetrievalStrategy:
        self.calls.append(question)
        return self.strategy


def build_use_case(
    *,
    chunks: list[RetrievedChunk] | None = None,
    graph_chunks: list[RetrievedChunk] | None = None,
    strategy: RetrievalStrategy = RetrievalStrategy.RAG,
    library: FakeLibraryRepository | None = None,
    index: _FakeIndexReader | None = None,
    cited: Sequence[str] = ("early",),
) -> tuple[
    AnswerQuestionUseCase,
    _FakeRetrievalRepository,
    _FakeAnswerProvider,
    _FakeRetriever,
]:
    repository = _FakeRetrievalRepository(
        [chunk("early", 0.1), chunk("boundary", 0.5)] if chunks is None else chunks
    )
    provider = _FakeAnswerProvider(cited)
    graph = _FakeRetriever([] if graph_chunks is None else graph_chunks)
    use_case = AnswerQuestionUseCase(
        library or FakeLibraryRepository(reading_state(0.5)),
        index or _FakeIndexReader(RagIndexState(RagIndexStatus.READY, MODEL)),
        RetrieveContextUseCase(repository, FakeEmbeddingProvider(), top_k=8),
        graph,
        _FakeClassifier(strategy),
        provider,
        embedding_model=MODEL,
    )
    return use_case, repository, provider, graph


def test_answers_at_the_stored_position() -> None:
    use_case, repository, *_ = build_use_case()

    result = asyncio.run(use_case.execute("owner", "book", "who is early"))

    assert result.position == 0.5
    assert repository.calls[0][1] == 0.5


def test_sources_are_only_the_chunks_the_answer_cited() -> None:
    use_case, _, *_ = build_use_case(
        chunks=[chunk("early", 0.1), chunk("boundary", 0.5)],
        cited=["boundary"],
    )

    result = asyncio.run(use_case.execute("owner", "book", "question"))

    assert [source.chunk_id for source in result.sources] == ["boundary"]


def test_citations_to_post_position_chunks_are_dropped() -> None:
    use_case, _, *_ = build_use_case(
        chunks=[chunk("early", 0.1), chunk("late", 0.9)],
        cited=["late", "early"],
    )

    result = asyncio.run(use_case.execute("owner", "book", "question"))

    assert [source.chunk_id for source in result.sources] == ["early"]


def test_source_metadata_comes_from_retrieval() -> None:
    use_case, _, *_ = build_use_case(
        chunks=[chunk("early", 0.1, chunk_index=7, distance=0.25)],
        cited=["early"],
    )

    result = asyncio.run(use_case.execute("owner", "book", "question"))

    source = result.sources[0]
    assert source.chunk_index == 7
    assert source.reading_position == 0.1
    assert source.distance == 0.25
    assert source.excerpt == "text-early"


def test_duplicate_citations_collapse_to_one_source_in_retrieval_order() -> None:
    use_case, _, *_ = build_use_case(
        chunks=[chunk("early", 0.1), chunk("boundary", 0.5)],
        cited=["boundary", "boundary", "early"],
    )

    result = asyncio.run(use_case.execute("owner", "book", "question"))

    assert [source.chunk_id for source in result.sources] == ["early", "boundary"]


def test_no_visible_chunks_answers_without_calling_the_model() -> None:
    use_case, _, provider, *_ = build_use_case(
        chunks=[chunk("late", 0.9)],
        cited=["late"],
    )

    result = asyncio.run(use_case.execute("owner", "book", "question"))

    assert result.sources == ()
    assert result.answer
    assert provider.calls == []


def test_unknown_book_raises_not_found() -> None:
    use_case, _, *_ = build_use_case(library=FakeLibraryRepository())

    with pytest.raises(BookNotFoundError):
        asyncio.run(use_case.execute("owner", "book", "question"))


@pytest.mark.parametrize("status", ["pending", "processing", "failed"])
def test_unprocessed_book_raises_not_ready(status: str) -> None:
    use_case, _, *_ = build_use_case(
        library=FakeLibraryRepository(reading_state(processing_status=status))
    )

    with pytest.raises(BookNotReadyError):
        asyncio.run(use_case.execute("owner", "book", "question"))


@pytest.mark.parametrize("status", [RagIndexStatus.READY, RagIndexStatus.PARTIAL])
def test_current_index_answers(status: RagIndexStatus) -> None:
    use_case, _, *_ = build_use_case(index=_FakeIndexReader(RagIndexState(status, MODEL)))

    result = asyncio.run(use_case.execute("owner", "book", "question"))

    assert [source.chunk_id for source in result.sources] == ["early"]


@pytest.mark.parametrize(
    ("index_state", "reason"),
    [
        (None, "missing"),
        (RagIndexState(RagIndexStatus.PENDING, MODEL), "pending"),
        (RagIndexState(RagIndexStatus.BUILDING, MODEL), "building"),
        (RagIndexState(RagIndexStatus.FAILED, MODEL), "failed"),
        (RagIndexState(RagIndexStatus.READY, "other-model"), "stale"),
    ],
)
def test_unusable_index_raises_before_embedding_or_answering(
    index_state: RagIndexState | None,
    reason: str,
) -> None:
    use_case, repository, provider, *_ = build_use_case(index=_FakeIndexReader(index_state))

    with pytest.raises(RagIndexNotReadyError) as error:
        asyncio.run(use_case.execute("owner", "book", "question"))

    assert error.value.reason == reason
    assert repository.calls == []
    assert provider.calls == []


def test_blank_question_is_rejected_before_embedding() -> None:
    use_case, repository, provider, *_ = build_use_case()

    with pytest.raises(ValueError):
        asyncio.run(use_case.execute("owner", "book", "   "))

    assert repository.calls == []
    assert provider.calls == []

def test_graph_strategy_uses_graph_retrieval_only() -> None:
    use_case, repository, _, graph = build_use_case(
        strategy=RetrievalStrategy.GRAPH,
        graph_chunks=[chunk("graph", 0.2)],
        cited=["graph"],
    )

    result = asyncio.run(use_case.execute("owner", "book", "who is early"))

    assert [source.chunk_id for source in result.sources] == ["graph"]
    assert repository.calls == []
    assert graph.calls == [("book", 0.5, "who is early")]


def test_graph_strategy_falls_back_to_rag_when_nothing_is_visible() -> None:
    use_case, repository, _, graph = build_use_case(
        strategy=RetrievalStrategy.GRAPH,
        graph_chunks=[chunk("late", 0.9)],
        cited=["early"],
    )

    result = asyncio.run(use_case.execute("owner", "book", "question"))

    assert graph.calls
    assert repository.calls
    assert [source.chunk_id for source in result.sources] == ["early"]
