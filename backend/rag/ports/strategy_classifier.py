"""Port for choosing a retrieval strategy from the question alone."""

from typing import Protocol

from rag.domain.retrieval import RetrievalStrategy


class StrategyClassifier(Protocol):
    async def classify_strategy(self, question: str) -> RetrievalStrategy: ...
