"""Answer generation port, independent of any language-model vendor."""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.chat import AnswerDraft
from rag.domain.retrieval import RetrievedChunk


class AnswerProvider(Protocol):
    async def answer(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
    ) -> AnswerDraft: ...
