"""Hierarchical Leiden community detection over the knowledge graph."""

import hashlib
import uuid
from dataclasses import asdict

import igraph
import leidenalg

from rag.domain.clustering import (
    ClusterGraph,
    ClusterParameters,
    Community,
    CommunityTree,
)


class LeidenCommunityDetector:
    def detect(
        self,
        graph: ClusterGraph,
        parameters: ClusterParameters,
    ) -> CommunityTree:
        nodes = sorted(graph.nodes, key=lambda node: node.node_id)
        if not nodes:
            return CommunityTree(
                communities=(),
                node_count=0,
                edge_count=0,
                modularity=None,
                algorithm="leiden",
                parameters=asdict(parameters),
            )

        vertex_index = {node.node_id: index for index, node in enumerate(nodes)}
        edges = [
            (vertex_index[edge.source_id], vertex_index[edge.target_id])
            for edge in graph.edges
            if edge.source_id in vertex_index and edge.target_id in vertex_index
        ]
        weights = [
            edge.weight
            for edge in graph.edges
            if edge.source_id in vertex_index and edge.target_id in vertex_index
        ]

        weighted_graph = igraph.Graph(n=len(nodes))
        weighted_graph.add_edges(edges)
        weighted_graph.es["weight"] = weights

        partition = _partition(weighted_graph, parameters)
        modularity = (
            float(partition.modularity)
            if parameters.objective == "modularity"
            else None
        )

        communities: list[Community] = []
        _collect(
            graph=weighted_graph,
            node_ids=[node.node_id for node in nodes],
            positions={node.node_id: node.reading_position for node in nodes},
            partition=partition,
            parent_id=None,
            level=0,
            parameters=parameters,
            book_id=graph.book_id,
            communities=communities,
        )

        return CommunityTree(
            communities=tuple(communities),
            node_count=len(nodes),
            edge_count=len(edges),
            modularity=modularity,
            algorithm="leiden",
            parameters=asdict(parameters),
        )


def _partition(graph: igraph.Graph, parameters: ClusterParameters):
    partition_type = (
        leidenalg.CPMVertexPartition
        if parameters.objective == "cpm"
        else leidenalg.RBConfigurationVertexPartition
    )
    return leidenalg.find_partition(
        graph,
        partition_type,
        weights="weight",
        resolution_parameter=parameters.resolution,
        n_iterations=-1,
        seed=parameters.seed,
    )


def _collect(
    *,
    graph: igraph.Graph,
    node_ids: list[str],
    positions: dict[str, float],
    partition,
    parent_id: str | None,
    level: int,
    parameters: ClusterParameters,
    book_id: str,
    communities: list[Community],
) -> None:
    groups = [sorted(group) for group in partition]
    for group in groups:
        member_ids = tuple(sorted(node_ids[index] for index in group))
        if not member_ids:
            continue
        seed_node_id = min(
            member_ids,
            key=lambda node_id: (positions[node_id], node_id),
        )
        community_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"community:{book_id}:{level}:{seed_node_id}",
            )
        )
        first_seen_position = min(positions[node_id] for node_id in member_ids)
        signature = hashlib.sha256(
            f"{level}:{','.join(member_ids)}".encode()
        ).hexdigest()
        communities.append(
            Community(
                community_id=community_id,
                parent_id=parent_id,
                level=level,
                member_ids=member_ids,
                seed_node_id=seed_node_id,
                first_seen_position=first_seen_position,
                internal_weight=_internal_weight(graph, group),
                signature_hash=signature,
            )
        )

        if level >= parameters.max_levels or len(group) < parameters.min_size:
            continue

        subgraph = graph.induced_subgraph(group)
        sub_partition = _partition(subgraph, parameters)
        if len(sub_partition) <= 1:
            continue

        sub_node_ids = [node_ids[index] for index in group]
        _collect(
            graph=subgraph,
            node_ids=sub_node_ids,
            positions=positions,
            partition=sub_partition,
            parent_id=community_id,
            level=level + 1,
            parameters=parameters,
            book_id=book_id,
            communities=communities,
        )


def _internal_weight(graph: igraph.Graph, group: list[int]) -> float:
    members = set(group)
    return float(
        sum(
            graph.es[index]["weight"]
            for index in range(graph.ecount())
            if graph.es[index].source in members and graph.es[index].target in members
        )
    )
