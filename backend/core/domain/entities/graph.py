"""Knowledge graph domain entities.

The graph is assembled from knowledge that is already tagged with a
``reading_position``. Nodes and edges are always derived from the mentions that
are visible at the reader's current position, never from a precomputed
book-wide summary.
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class GraphNode:
    """A resolved entity visible at the requested reading position."""

    node_id: str
    label: str
    node_type: str
    first_seen_position: float
    mention_count: int
    description: str = ""
    sub_type: str | None = None
    aliases: tuple[str, ...] = ()
    importance: int | None = None


@dataclass(frozen=True)
class GraphEdge:
    """A fact linking two visible nodes, traceable to the chunk it came from."""

    edge_id: str
    source_id: str
    target_id: str
    statement: str
    position: float
    chunk_id: str


@dataclass(frozen=True)
class BookGraph:
    """The spoiler-filtered graph for one book at one reading position."""

    book_id: str
    position: float
    revision: int
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


@dataclass(frozen=True)
class EntityMention:
    """One entity mention, already filtered to the reader's visible range.

    ``canonical_id`` is an internal pointer, never a name, so a node cannot
    inherit a label the reader has not seen yet.
    """

    entity_id: str
    canonical_id: str
    name: str
    entity_type: str
    reading_position: float
    description: str = ""
    sub_type: str | None = None
    aliases: tuple[str, ...] = ()
    importance: int | None = None


@dataclass(frozen=True)
class FactLink:
    """A fact that may become an edge, with its subject and object as raw text."""

    fact_id: str
    chunk_id: str
    statement: str
    subject: str | None
    object: str | None
    reading_position: float


@dataclass(frozen=True)
class BookGraphState:
    """Stored graph and progress facts needed to decide whether work is due."""

    book_id: str
    progress_position: float
    processing_status: str
    graph_revision: int


@dataclass(frozen=True)
class EntityCandidate:
    """An entity mention offered to the resolver for identity grouping."""

    entity_id: str
    name: str
    entity_type: str
    reading_position: float


@dataclass(frozen=True)
class EntityResolution:
    """The outcome of resolving mentions into canonical entities."""

    canonical_by_entity: Mapping[str, str]
    method_by_entity: Mapping[str, str]
    changed: bool
