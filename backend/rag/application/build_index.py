"""Build the embeddings and community index for one book."""

import logging

from rag.application.embeddings import EmbedKnowledgeService
from rag.clustering.service import CommunityBuilder
from rag.domain.embeddings import EmbeddingSummary
from rag.ports.rag_repository import RagRepository

logger = logging.getLogger(__name__)


class BuildRagIndexUseCase:
    def __init__(
        self,
        repository: RagRepository,
        embeddings: EmbedKnowledgeService,
        communities: CommunityBuilder,
        embedding_model: str,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._communities = communities
        self._embedding_model = embedding_model

    async def execute(self, book_id: str, graph_revision: int) -> EmbeddingSummary | None:
        await self._repository.mark_building(
            book_id, graph_revision, self._embedding_model
        )
        try:
            summary = await self._embeddings.embed_book(book_id)
            await self._communities.build(
                book_id,
                graph_revision,
                self._embedding_model,
            )
        except Exception as error:
            logger.exception("RAG indexing failed for book %s", book_id)
            await self._repository.mark_failed(book_id, str(error))
            return None
        logger.info(
            "RAG index ready for book %s: sources=%d embedded=%d reused=%d",
            book_id,
            summary.total,
            summary.embedded,
            summary.reused,
        )
        return summary
