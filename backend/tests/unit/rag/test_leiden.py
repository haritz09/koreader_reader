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


def test_isolated_nodes_do_not_become_singleton_communities() -> None:
    graph = ClusterGraph(
        book_id="book-1",
        nodes=tuple(
            (
                *complete_graph("a", [0.0, 0.1, 0.2, 0.3]),
                ClusterNode(
                    node_id="lonely",
                    node_type="character",
                    label="Lonely",
                    reading_position=0.9,
                    mention_count=1,
                ),
            )
        ),
        edges=tuple(complete_edges("a", 4)),
    )

    tree = LeidenCommunityDetector().detect(graph, PARAMETERS)

    assert tree.communities
    assert all(len(community.member_ids) >= 2 for community in tree.communities)
    assert tree.parameters["unclustered_nodes"] == 1


def test_max_levels_counts_total_levels(monkeypatch) -> None:
    import rag.clustering.leiden as leiden_module

    def fake_partition(graph, parameters):
        size = graph.vcount()
        if size == 8:
            return [[0, 1, 2, 3], [4, 5, 6, 7]]
        if size == 4:
            return [[0, 1], [2, 3]]
        if size == 2:
            return [[0], [1]]
        return [[0]]

    monkeypatch.setattr(leiden_module, "_partition", fake_partition)

    nodes = tuple(complete_graph("a", [index / 10 for index in range(8)]))
    graph = ClusterGraph(
        book_id="book-1",
        nodes=nodes,
        edges=tuple(
            ClusterEdge(source_id=f"a{index}", target_id=f"a{index + 1}", weight=1.0)
            for index in range(7)
        ),
    )

    def levels(max_levels: int) -> set[int]:
        parameters = ClusterParameters(
            resolution=1.0,
            max_levels=max_levels,
            min_size=1,
            min_members=1,
            seed=42,
            objective="cpm",
            fact_edge_weight=2.0,
            cooccurrence_edge_weight=1.0,
        )
        tree = LeidenCommunityDetector().detect(graph, parameters)
        return {community.level for community in tree.communities}

    assert levels(3) == {0, 1, 2}
    assert levels(2) == {0, 1}
