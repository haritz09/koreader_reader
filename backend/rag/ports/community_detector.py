"""Community detection port."""

from typing import Protocol

from rag.domain.clustering import ClusterGraph, ClusterParameters, CommunityTree


class CommunityDetector(Protocol):
    def detect(
        self,
        graph: ClusterGraph,
        parameters: ClusterParameters,
    ) -> CommunityTree: ...
