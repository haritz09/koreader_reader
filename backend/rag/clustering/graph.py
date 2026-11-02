"""Build the weighted knowledge graph used for community detection."""

from collections import defaultdict
from itertools import combinations

from core.services.entity_resolution import normalize_name
from rag.domain.clustering import (
    ClusterEdge,
    ClusterEntityMention,
    ClusterGraph,
    ClusterNamedMention,
    ClusterNode,
    ClusterParameters,
    ClusterSources,
)


def _node_id_for_named(mention: ClusterNamedMention) -> str | None:
    key = normalize_name(mention.name)
    if not key:
        return None
    return f"{mention.node_type}:{key}"


def build_cluster_graph(
    book_id: str,
    sources: ClusterSources,
    parameters: ClusterParameters,
) -> ClusterGraph:
    entity_groups: dict[str, list[ClusterEntityMention]] = defaultdict(list)
    for mention in sources.entity_mentions:
        entity_groups[mention.canonical_id or mention.entity_id].append(mention)

    named_groups: dict[str, list[ClusterNamedMention]] = defaultdict(list)
    for mention in sources.named_mentions:
        node_id = _node_id_for_named(mention)
        if node_id is not None:
            named_groups[node_id].append(mention)

    nodes: list[ClusterNode] = []
    node_names: dict[str, list[str]] = defaultdict(list)
    chunk_nodes: dict[str, set[str]] = defaultdict(set)

    for node_id, mentions in entity_groups.items():
        ordered = sorted(
            mentions, key=lambda mention: (mention.reading_position, mention.entity_id)
        )
        earliest = ordered[0]
        nodes.append(
            ClusterNode(
                node_id=node_id,
                node_type=earliest.entity_type,
                label=earliest.name,
                reading_position=earliest.reading_position,
                mention_count=len(ordered),
            )
        )
        for mention in ordered:
            node_names[node_id].extend((mention.name, *mention.aliases))
            chunk_nodes[mention.chunk_id].add(node_id)

    for node_id, mentions in named_groups.items():
        ordered = sorted(
            mentions, key=lambda mention: (mention.reading_position, mention.mention_id)
        )
        earliest = ordered[0]
        nodes.append(
            ClusterNode(
                node_id=node_id,
                node_type=earliest.node_type,
                label=earliest.name,
                reading_position=earliest.reading_position,
                mention_count=len(ordered),
            )
        )
        for mention in ordered:
            node_names[node_id].append(mention.name)
            chunk_nodes[mention.chunk_id].add(node_id)

    nodes.sort(key=lambda node: (node.reading_position, node.node_id))

    name_index: dict[str, str | None] = {}
    for node_id, names in node_names.items():
        for name in names:
            key = normalize_name(name)
            if not key:
                continue
            current = name_index.get(key)
            if key in name_index and current != node_id:
                name_index[key] = None
            else:
                name_index[key] = node_id

    edge_weights: dict[tuple[str, str], float] = defaultdict(float)
    for node_ids in chunk_nodes.values():
        ordered = sorted(node_ids)
        if len(ordered) > parameters.max_nodes_per_chunk:
            ordered = ordered[: parameters.max_nodes_per_chunk]
        for source_id, target_id in combinations(ordered, 2):
            edge_weights[(source_id, target_id)] += parameters.cooccurrence_edge_weight

    for fact in sources.facts:
        if not fact.subject or not fact.object:
            continue
        source_id = name_index.get(normalize_name(fact.subject))
        target_id = name_index.get(normalize_name(fact.object))
        if source_id is None or target_id is None or source_id == target_id:
            continue
        key = tuple(sorted((source_id, target_id)))
        edge_weights[key] += parameters.fact_edge_weight

    edges = tuple(
        ClusterEdge(source_id=source_id, target_id=target_id, weight=weight)
        for (source_id, target_id), weight in sorted(edge_weights.items())
    )
    return ClusterGraph(book_id=book_id, nodes=tuple(nodes), edges=edges)
