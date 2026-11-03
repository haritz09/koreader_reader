"""Build the embeddings and community index for one book."""

import logging

from rag.application.embeddings import EmbedKnowledgeService
from rag.clustering.service import CommunityBuilder
from rag.domain.embeddings import EmbeddingSummary
from rag.domain.errors import (
    EmbeddingConfigurationError,
    EmbeddingPermanentError,
    EmbeddingQuotaExhaustedError,
    RagBuildDeferred,
)
from rag.ports.rag_repository import RagRepository

logger = logging.getLogger(__name__)


class BuildRagIndexUseCase:
    def __init__(
        self,
        repository: RagRepository,
        embeddings: EmbedKnowledgeService,
        communities: CommunityBuilder,
        embedding_model: str,
        *,
        stale_after_seconds: int,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._communities = communities
        self._embedding_model = embedding_model
        self._stale_after_seconds = stale_after_seconds

    async def execute(self, book_id: str, graph_revision: int) -> EmbeddingSummary | None:
        claimed = await self._repository.claim_build(
            book_id,
            graph_revision,
            self._embedding_model,
            self._stale_after_seconds,
        )
        if not claimed:
            logger.info("RAG index build for book %s is already running", book_id)
            return None
        try:
            summary = await self._embeddings.embed_book(book_id)
            await self._communities.build(
                book_id,
                graph_revision,
                self._embedding_model,
            )
        except EmbeddingQuotaExhaustedError as error:
            logger.warning("RAG indexing deferred for book %s: %s", book_id, error)
            await self._repository.mark_pending(book_id, str(error))
            raise RagBuildDeferred(error.retry_after) from error
        except (EmbeddingConfigurationError, EmbeddingPermanentError) as error:
            logger.exception("RAG indexing failed permanently for book %s", book_id)
            await self._repository.mark_failed(book_id, str(error))
            return None
        except Exception as error:
            logger.exception("RAG indexing failed for book %s", book_id)
            await self._repository.mark_failed(book_id, str(error))
            raise
        logger.info(
            "RAG index ready for book %s: sources=%d embedded=%d reused=%d skipped=%d",
            book_id,
            summary.total,
            summary.embedded,
            summary.reused,
            summary.skipped,
        )
        return summary
