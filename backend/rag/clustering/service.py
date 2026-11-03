"""Application service that materializes a book's community index."""

from rag.clustering.graph import build_cluster_graph
from rag.domain.clustering import ClusterParameters, CommunityTree
from rag.domain.status import RagIndexStatus
from rag.ports.community_detector import CommunityDetector
from rag.ports.rag_repository import RagRepository


class CommunityBuilder:
    def __init__(
        self,
        repository: RagRepository,
        detector: CommunityDetector,
        parameters: ClusterParameters,
    ) -> None:
        self._repository = repository
        self._detector = detector
        self._parameters = parameters

    async def build(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        *,
        status: RagIndexStatus = RagIndexStatus.READY,
        error: str | None = None,
    ) -> CommunityTree:
        sources = await self._repository.get_cluster_sources(book_id)
        graph = build_cluster_graph(book_id, sources, self._parameters)
        tree = self._detector.detect(graph, self._parameters)
        await self._repository.save_community_run(
            book_id,
            graph_revision,
            embedding_model,
            graph,
            tree,
            status,
            error,
        )
        return tree
