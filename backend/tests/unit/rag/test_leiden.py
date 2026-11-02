"""Hierarchical Leiden community detection."""

from rag.clustering.leiden import LeidenCommunityDetector
from rag.domain.clustering import ClusterEdge, ClusterGraph, ClusterNode, ClusterParameters

PARAMETERS = ClusterParameters(
    resolution=1.0,
    max_levels=2,
    min_size=2,
    seed=42,
    objective="modularity",
    fact_edge_weight=2.0,
    cooccurrence_edge_weight=1.0,
)


def complete_graph(prefix: str, positions: list[float]) -> list[ClusterNode]:
    return [
        ClusterNode(
            node_id=f"{prefix}{index}",
            node_type="character",
            label=f"{prefix}{index}",
            reading_position=position,
            mention_count=1,
        )
        for index, position in enumerate(positions)
    ]


def complete_edges(prefix: str, size: int) -> list[ClusterEdge]:
    return [
        ClusterEdge(
            source_id=f"{prefix}{left}",
            target_id=f"{prefix}{right}",
            weight=1.0,
        )
        for left in range(size)
        for right in range(left + 1, size)
    ]


def test_disconnected_cliques_become_separate_root_communities() -> None:
    graph = ClusterGraph(
        book_id="book-1",
        nodes=tuple(
            complete_graph("a", [0.0, 0.1, 0.2, 0.3])
            + complete_graph("b", [0.5, 0.6, 0.7, 0.8])
        ),
        edges=tuple(complete_edges("a", 4) + complete_edges("b", 4)),
    )

    tree = LeidenCommunityDetector().detect(graph, PARAMETERS)

    roots = [community for community in tree.communities if community.level == 0]
    assert len(roots) == 2
    assert sorted(len(community.member_ids) for community in roots) == [4, 4]
    assert {node_id for community in roots for node_id in community.member_ids} == {
        node.node_id for node in graph.nodes
    }

    positions = {node.node_id: node.reading_position for node in graph.nodes}
    for community in roots:
        expected_first = min(positions[node_id] for node_id in community.member_ids)
        expected_seed = min(
            community.member_ids,
            key=lambda node_id: (positions[node_id], node_id),
        )
        assert community.first_seen_position == expected_first
        assert community.seed_node_id == expected_seed

    by_id = {community.community_id: community for community in tree.communities}
    for community in tree.communities:
        if community.parent_id is None:
            continue
        parent = by_id[community.parent_id]
        assert community.level == parent.level + 1
        assert set(community.member_ids) <= set(parent.member_ids)


def test_detection_is_reproducible() -> None:
    graph = ClusterGraph(
        book_id="book-1",
        nodes=tuple(complete_graph("a", [0.0, 0.1, 0.2]) + complete_graph("b", [0.5, 0.6])),
        edges=tuple(complete_edges("a", 3) + complete_edges("b", 2)),
    )

    first = LeidenCommunityDetector().detect(graph, PARAMETERS)
    second = LeidenCommunityDetector().detect(graph, PARAMETERS)

    assert first == second
