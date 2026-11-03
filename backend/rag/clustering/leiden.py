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

UNCLUSTERED_NODES_KEY = "unclustered_nodes"


class LeidenCommunityDetector:
    def detect(
        self,
        graph: ClusterGraph,
        parameters: ClusterParameters,
    ) -> CommunityTree:
        nodes = sorted(graph.nodes, key=lambda node: node.node_id)
        if not nodes:
            empty_parameters = asdict(parameters)
            empty_parameters[UNCLUSTERED_NODES_KEY] = 0
            return CommunityTree(
                communities=(),
                node_count=0,
                edge_count=0,
                modularity=None,
                algorithm="leiden",
                parameters=empty_parameters,
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

        kept = _keep_sized_communities(communities, parameters.min_members)
        covered = {node_id for community in kept for node_id in community.member_ids}
        run_parameters = asdict(parameters)
        run_parameters[UNCLUSTERED_NODES_KEY] = len(nodes) - len(covered)

        return CommunityTree(
            communities=tuple(kept),
            node_count=len(nodes),
            edge_count=len(edges),
            modularity=modularity,
            algorithm="leiden",
            parameters=run_parameters,
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
    internal_weights = _internal_weights(graph, groups)
    for group, internal_weight in zip(groups, internal_weights, strict=True):
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
                internal_weight=internal_weight,
                signature_hash=signature,
            )
        )

        if level + 1 >= parameters.max_levels or len(group) < parameters.min_size:
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


def _internal_weights(
    graph: igraph.Graph,
    groups: list[list[int]],
) -> list[float]:
    adjacency: list[list[tuple[int, float]]] = [[] for _ in range(graph.vcount())]
    for edge in graph.es:
        adjacency[edge.source].append((edge.target, edge["weight"]))

    weights: list[float] = []
    for group in groups:
        members = set(group)
        weights.append(
            float(
                sum(
                    weight
                    for source in group
                    for target, weight in adjacency[source]
                    if target in members
                )
            )
        )
    return weights


def _keep_sized_communities(
    communities: list[Community],
    min_members: int,
) -> list[Community]:
    parents = {
        community.parent_id for community in communities if community.parent_id is not None
    }
    return [
        community
        for community in communities
        if len(community.member_ids) >= min_members or community.community_id in parents
    ]
