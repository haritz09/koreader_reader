"""Answer a question from evidence the reader has already reached."""

from core.domain.errors import BookNotFoundError, BookNotReadyError
from core.domain.status import GRAPH_STATUSES
from core.ports.library_repository import LibraryRepository
from core.ports.llm_provider import LLMError
from rag.domain.chat import AnswerDraft, ChatAnswer, ChatSource
from rag.domain.errors import RagIndexNotReadyError
from rag.domain.index_state import RagIndexState
from rag.domain.retrieval import RetrievalResult, RetrievalStrategy, RetrievedChunk
from rag.domain.status import RAG_INDEX_CURRENT_STATUSES
from rag.ports.answer_provider import AnswerProvider
from rag.ports.context_retriever import ContextRetriever
from rag.ports.index_state import RagIndexReader
from rag.ports.strategy_classifier import StrategyClassifier

MAX_EXCERPT_CHARS = 400
NO_EVIDENCE_ANSWER = "No visible text in this book answers that question yet."


class AnswerQuestionUseCase:
    def __init__(
        self,
        library: LibraryRepository,
        index: RagIndexReader,
        rag: ContextRetriever,
        graph: ContextRetriever,
        classifier: StrategyClassifier,
        answers: AnswerProvider,
        *,
        embedding_model: str,
    ) -> None:
        self._library = library
        self._index = index
        self._rag = rag
        self._graph = graph
        self._classifier = classifier
        self._answers = answers
        self._embedding_model = embedding_model

    async def execute(
        self,
        owner_id: str,
        book_id: str,
        question: str,
    ) -> ChatAnswer:
        text = question.strip()
        if not text:
            raise ValueError("Question must not be blank")

        state = await self._library.get_reading_state(owner_id, book_id)
        if state is None:
            raise BookNotFoundError(book_id)
        if state.processing_status not in GRAPH_STATUSES:
            raise BookNotReadyError(state.processing_status)

        await self._require_current_index(book_id)

        context = await self._retrieve(text, book_id, state.progress_position)
        if not context.chunks:
            return ChatAnswer(
                book_id=book_id,
                position=context.position,
                model=context.model,
                answer=NO_EVIDENCE_ANSWER,
                sources=(),
            )

        draft = await self._answers.answer(text, context.chunks)
        return ChatAnswer(
            book_id=book_id,
            position=context.position,
            model=context.model,
            answer=draft.text,
            sources=_cited_sources(context.chunks, draft),
        )

    async def _retrieve(
        self,
        question: str,
        book_id: str,
        position: float,
    ) -> RetrievalResult:
        if await self._classify(question) is RetrievalStrategy.GRAPH:
            context = await self._graph.execute(book_id, position, question)
            if context.chunks:
                return context
        return await self._rag.execute(book_id, position, question)

    async def _classify(self, question: str) -> RetrievalStrategy:
        try:
            return await self._classifier.classify_strategy(question)
        except LLMError:
            return RetrievalStrategy.RAG

    async def _require_current_index(self, book_id: str) -> None:
        index = await self._index.get_index_state(book_id)
        _raise_unless_usable(index, self._embedding_model)


def _raise_unless_usable(
    index: RagIndexState | None,
    embedding_model: str,
) -> None:
    if index is None:
        raise RagIndexNotReadyError("missing")
    if index.status not in RAG_INDEX_CURRENT_STATUSES:
        raise RagIndexNotReadyError(index.status.value)
    if index.embedding_model != embedding_model:
        raise RagIndexNotReadyError("stale")


def _cited_sources(
    chunks: tuple[RetrievedChunk, ...],
    draft: AnswerDraft,
) -> tuple[ChatSource, ...]:
    cited = set(draft.cited_chunk_ids)
    return tuple(
        ChatSource(
            chunk_id=chunk.chunk_id,
            chunk_index=chunk.chunk_index,
            reading_position=chunk.reading_position,
            distance=chunk.distance,
            excerpt=chunk.text[:MAX_EXCERPT_CHARS],
        )
        for chunk in chunks
        if chunk.chunk_id in cited
    )
