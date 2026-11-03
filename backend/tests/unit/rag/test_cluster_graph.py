"""Cluster graph construction from stored knowledge."""

import pytest

from core.domain.entities.knowledge import EVENT_NODE_TYPE, LOCATION_NODE_TYPE
from rag.clustering.graph import build_cluster_graph
from rag.domain.clustering import (
    ClusterEntityMention,
    ClusterFact,
    ClusterNamedMention,
    ClusterParameters,
    ClusterSources,
)

PARAMETERS = ClusterParameters(
    resolution=1.0,
    max_levels=2,
    min_size=2,
    seed=42,
    objective="modularity",
    fact_edge_weight=2.0,
    cooccurrence_edge_weight=1.0,
)


def entity(
    entity_id: str,
    canonical_id: str,
    name: str,
    chunk_id: str,
    position: float,
    aliases: tuple[str, ...] = (),
) -> ClusterEntityMention:
    return ClusterEntityMention(
        entity_id=entity_id,
        canonical_id=canonical_id,
        name=name,
        entity_type="character",
        aliases=aliases,
        reading_position=position,
        chunk_id=chunk_id,
    )


def named(
    mention_id: str,
    name: str,
    node_type: str,
    chunk_id: str,
    position: float,
) -> ClusterNamedMention:
    return ClusterNamedMention(
        mention_id=mention_id,
        name=name,
        node_type=node_type,
        reading_position=position,
        chunk_id=chunk_id,
    )


def fact(
    subject: str,
    object_: str,
) -> ClusterFact:
    return ClusterFact(
        subject=subject,
        object=object_,
    )


def edge_weight(graph, source: str, target: str) -> float:
    pair = {source, target}
    return next(
        edge.weight
        for edge in graph.edges
        if {edge.source_id, edge.target_id} == pair
    )


def test_mentions_collapse_into_canonical_nodes_and_edges_accumulate() -> None:
    sources = ClusterSources(
        entity_mentions=(
            entity("e1", "c1", "Alice", "ck1", 0.1),
            entity("e2", "c1", "Al", "ck2", 0.2, aliases=("Ally",)),
            entity("e3", "c2", "Bob", "ck1", 0.1),
            entity("e4", "c3", "Carol", "ck2", 0.2),
        ),
        named_mentions=(
            named("l1", "Paris", LOCATION_NODE_TYPE, "ck1", 0.1),
            named("ev1", "Duel", EVENT_NODE_TYPE, "ck1", 0.1),
        ),
        facts=(
            fact("Alice", "Bob"),
            fact("Alice", "Unknown"),
            fact("Paris", "Duel"),
        ),
    )

    graph = build_cluster_graph("book-1", sources, PARAMETERS)

    nodes = {node.node_id: node for node in graph.nodes}
    assert set(nodes) == {"c1", "c2", "c3", "location:paris", "event:duel"}
    assert nodes["c1"].label == "Alice"
    assert nodes["c1"].mention_count == 2
    assert nodes["c1"].reading_position == 0.1

    assert edge_weight(graph, "c1", "c2") == pytest.approx(3.0)
    assert edge_weight(graph, "c1", "c3") == pytest.approx(1.0)
    assert edge_weight(graph, "location:paris", "event:duel") == pytest.approx(3.0)
    assert all(
        "unknown" not in node.node_id.lower() for node in graph.nodes
    )


def test_ambiguous_names_do_not_create_fact_edges() -> None:
    sources = ClusterSources(
        entity_mentions=(
            entity("e1", "c1", "Paris", "ck1", 0.1),
            entity("e2", "c2", "Bob", "ck1", 0.1),
        ),
        named_mentions=(named("l1", "Paris", LOCATION_NODE_TYPE, "ck1", 0.1),),
        facts=(fact("Paris", "Bob"),),
    )

    graph = build_cluster_graph("book-1", sources, PARAMETERS)

    assert edge_weight(graph, "c1", "c2") == pytest.approx(1.0)
    assert edge_weight(graph, "c1", "location:paris") == pytest.approx(1.0)
    assert edge_weight(graph, "location:paris", "c2") == pytest.approx(1.0)


def test_graph_output_is_deterministic() -> None:
    sources = ClusterSources(
        entity_mentions=(
            entity("e2", "c2", "Bob", "ck1", 0.2),
            entity("e1", "c1", "Alice", "ck1", 0.1),
        ),
        named_mentions=(),
        facts=(fact("Alice", "Bob"),),
    )

    first = build_cluster_graph("book-1", sources, PARAMETERS)
    second = build_cluster_graph("book-1", sources, PARAMETERS)

    assert first == second
    assert [node.node_id for node in first.nodes] == ["c1", "c2"]


def test_chunk_truncation_keeps_the_most_mentioned_nodes() -> None:
    sources = ClusterSources(
        entity_mentions=(
            entity("e1", "c1", "Rare", "ck1", 0.1),
            entity("e2", "c2", "Common", "ck1", 0.2),
            entity("e3", "c2", "Common", "ck1", 0.2),
            entity("e4", "c2", "Common", "ck1", 0.2),
            entity("e5", "c3", "Middle", "ck1", 0.3),
            entity("e6", "c3", "Middle", "ck1", 0.3),
        ),
        named_mentions=(),
        facts=(),
    )
    parameters = ClusterParameters(
        resolution=1.0,
        max_levels=2,
        min_size=2,
        seed=42,
        objective="modularity",
        fact_edge_weight=2.0,
        cooccurrence_edge_weight=1.0,
        max_nodes_per_chunk=2,
    )

    graph = build_cluster_graph("book-1", sources, parameters)

    assert edge_weight(graph, "c2", "c3") == pytest.approx(1.0)
    assert all("c1" not in {edge.source_id, edge.target_id} for edge in graph.edges)
