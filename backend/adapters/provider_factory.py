"""Build the LLM and embedding providers shared by the API and the worker."""

import logging

from adapters.llm.failover_provider import FailoverLLMProvider
from adapters.llm.mock_provider import MockLLMProvider
from adapters.llm.openai_provider import OpenAIProvider
from core.config import settings
from rag.adapters.embeddings.gemini import GeminiEmbeddingProvider
from rag.adapters.embeddings.mock import MockEmbeddingProvider
from rag.domain.embeddings import EMBEDDING_DIMENSIONS
from rag.ports.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


def llm_models() -> list[str]:
    models = [settings.llm_model]
    models.extend(settings.llm_fallback_models.split(","))
    return list(dict.fromkeys(model.strip() for model in models if model.strip()))


def build_llm_provider() -> FailoverLLMProvider | MockLLMProvider:
    if settings.llm_provider == "mock":
        if not settings.allow_mock_llm:
            raise RuntimeError("LLM_PROVIDER=mock requires ALLOW_MOCK_LLM=true")
        logger.warning(
            "Mock LLM provider enabled; extraction will return empty knowledge"
        )
        return MockLLMProvider()
    return FailoverLLMProvider(
        [OpenAIProvider(model=model) for model in llm_models()]
    )


def build_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise RuntimeError(f"EMBEDDING_DIMENSIONS must be {EMBEDDING_DIMENSIONS}")
    if settings.embedding_provider == "mock":
        if not settings.allow_mock_embeddings:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=mock requires ALLOW_MOCK_EMBEDDINGS=true"
            )
        logger.warning("Mock embedding provider enabled; vectors are deterministic")
        return MockEmbeddingProvider()
    return GeminiEmbeddingProvider()
