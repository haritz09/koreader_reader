"""Spoiler-filtered graph assembly.

The repository filters by ``reading_position`` before anything reaches this
service. Assembly keeps that guarantee at the shape level:
* an edge is emitted only when both endpoints resolve to a visible node.
* an ambiguous normalized name drops the edge instead of guessing.
"""

import logging
from collections.abc import Mapping

from core.domain.entities.graph import BookGraph, EntityMention, FactLink, GraphEdge, GraphNode
from core.domain.entities.knowledge import EVENT_NODE_TYPE, LOCATION_NODE_TYPE
from core.domain.value_objects.reading_position import validate_reading_position
from core.ports.graph_repository import GraphRepository
from core.services.entity_resolution import normalize_name

logger = logging.getLogger(__name__)

# Places and events have no canonical pointer, so they group by name at read time.
_NAME_GROUPED_NODE_TYPES = frozenset({LOCATION_NODE_TYPE, EVENT_NODE_TYPE})


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


def _group_key(mention: EntityMention) -> tuple[str, str]:
    """Group entities by resolved identity, places and events by their name."""
    if mention.entity_type in _NAME_GROUPED_NODE_TYPES:
        return (mention.entity_type, normalize_name(mention.name))
    return ("entity", mention.canonical_id)


def _detail_of(
    ordered: list[EntityMention],
) -> tuple[str, str | None, tuple[str, ...], int | None]:
    """Derive description, sub type, aliases, and importance from visible mentions only."""
    description = next((m.description for m in ordered if m.description), "")
    sub_type = next((m.sub_type for m in ordered if m.sub_type), None)

    aliases: list[str] = []
    seen = {normalize_name(ordered[0].name)}
    for mention in ordered:
        for candidate in (mention.name, *mention.aliases):
            key = normalize_name(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            aliases.append(candidate)
    importance = min(
        (m.importance for m in ordered if m.importance is not None),
        default=None,
    )
    return description, sub_type, tuple(aliases), importance


def _build_nodes(
    mentions: list[EntityMention],
) -> tuple[list[GraphNode], dict[str, str | None]]:
    """Group visible mentions into nodes and index their names for edge lookup."""
    grouped: dict[tuple[str, str], list[EntityMention]] = {}
    for mention in mentions:
        grouped.setdefault(_group_key(mention), []).append(mention)

    nodes: list[GraphNode] = []
    name_index: dict[str, str | None] = {}
    for group in grouped.values():
        ordered = sorted(group, key=lambda m: (m.reading_position, m.entity_id))
        earliest = ordered[0]
        description, sub_type, aliases, importance = _detail_of(ordered)
        nodes.append(
            GraphNode(
                node_id=earliest.canonical_id,
                label=earliest.name,
                node_type=earliest.entity_type,
                first_seen_position=earliest.reading_position,
                mention_count=len(ordered),
                description=description,
                sub_type=sub_type,
                aliases=aliases,
                importance=importance,
            )
        )
        key = normalize_name(earliest.name)
        if key in name_index:
            name_index[key] = None
        else:
            name_index[key] = earliest.canonical_id

    nodes.sort(key=lambda node: (node.first_seen_position, node.node_id))
    return nodes, name_index


def _build_edges(
    facts: list[FactLink],
    name_index: Mapping[str, str | None],
) -> list[GraphEdge]:
    """Turn facts into edges between visible nodes.

    Facts with a missing, unresolvable, ambiguous, or self-referential endpoint
    are dropped rather than anchored to a placeholder node.
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
