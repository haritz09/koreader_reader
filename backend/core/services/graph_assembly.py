"""Spoiler-filtered graph assembly.

The repository applies ``reading_position <= reading_position`` so no
post-position knowledge can reach this service. Assembly then keeps that
guarantee intact at the shape level, which is where a leak would actually
happen:

* a node's label and ``first_seen_position`` come from the visible mentions of
  that node, never from a name stored on the canonical entity. An alias first
  mentioned at 0.8 therefore cannot label a node a reader sees at 0.3.
* an edge is emitted only when both of its endpoints resolve to a node that is
  visible. A fact at 0.2 pointing at a character first seen at 0.7 yields no
  edge rather than a dangling reference to something the reader cannot see.
* when a normalized name is ambiguous across visible nodes the edge is dropped
  instead of guessing which entity was meant.
"""

import logging
from collections.abc import Mapping

from core.domain.entities.graph import BookGraph, EntityMention, FactLink, GraphEdge, GraphNode
from core.domain.value_objects.reading_position import validate_reading_position
from core.ports.graph_repository import GraphRepository
from core.services.entity_resolution import normalize_name

logger = logging.getLogger(__name__)


class GraphAssemblyService:
    def __init__(self, graph_repository: GraphRepository) -> None:
        self._graph_repository = graph_repository

    async def build(self, book_id: str, reading_position: float) -> BookGraph:
        position = validate_reading_position(reading_position)
        mentions = await self._graph_repository.get_visible_mentions(book_id, position)
        facts = await self._graph_repository.get_visible_facts(book_id, position)
        revision = await self._graph_repository.get_revision(book_id)

        nodes, name_index = _build_nodes(mentions)
        edges = _build_edges(facts, name_index)
        return BookGraph(
            book_id=book_id,
            position=position,
            revision=revision,
            nodes=tuple(nodes),
            edges=tuple(edges),
        )


def _build_nodes(
    mentions: list[EntityMention],
) -> tuple[list[GraphNode], dict[str, str | None]]:
    """Group visible mentions into nodes and index their names for edge lookup."""
    grouped: dict[str, list[EntityMention]] = {}
    for mention in mentions:
        grouped.setdefault(mention.canonical_id, []).append(mention)

    nodes: list[GraphNode] = []
    name_index: dict[str, str | None] = {}
    for canonical_id, group in grouped.items():
        ordered = sorted(group, key=lambda m: (m.reading_position, m.entity_id))
        earliest = ordered[0]
        nodes.append(
            GraphNode(
                node_id=canonical_id,
                label=earliest.name,
                node_type=earliest.entity_type,
                first_seen_position=earliest.reading_position,
                mention_count=len(ordered),
            )
        )
        key = normalize_name(earliest.name)
        if key in name_index:
            name_index[key] = None
        else:
            name_index[key] = canonical_id

    nodes.sort(key=lambda node: (node.first_seen_position, node.node_id))
    return nodes, name_index


def _build_edges(
    facts: list[FactLink],
    name_index: Mapping[str, str | None],
) -> list[GraphEdge]:
    """Turn facts into edges between visible nodes.

    Facts whose subject or object is missing, unresolvable, or ambiguous among
    visible nodes are skipped. A single-sided fact is not representable as an
    edge between two entities, so it is dropped rather than anchored to a
    placeholder node.
    """
    edges: list[GraphEdge] = []
    seen: set[tuple[str, str, str]] = set()
    for fact in sorted(facts, key=lambda f: (f.reading_position, f.fact_id)):
        if not fact.subject or not fact.object:
            continue
        source_id = name_index.get(normalize_name(fact.subject))
        target_id = name_index.get(normalize_name(fact.object))
        if source_id is None or target_id is None:
            continue
        if source_id == target_id:
            continue
        key = (source_id, target_id, fact.fact_id)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            GraphEdge(
                edge_id=fact.fact_id,
                source_id=source_id,
                target_id=target_id,
                statement=fact.statement,
                position=fact.reading_position,
                chunk_id=fact.chunk_id,
            )
        )
    return edges
