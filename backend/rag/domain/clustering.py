"""Graph and community types used by the clustering stage."""

from dataclasses import dataclass
from typing import Literal

ClusterObjective = Literal["modularity", "cpm"]


@dataclass(frozen=True)
class ClusterEntityMention:
    entity_id: str
    canonical_id: str
    name: str
    entity_type: str
    aliases: tuple[str, ...]
    reading_position: float
    chunk_id: str


@dataclass(frozen=True)
class ClusterNamedMention:
    mention_id: str
    name: str
    node_type: str
    reading_position: float
    chunk_id: str


@dataclass(frozen=True)
class ClusterFact:
    subject: str | None
    object: str | None


@dataclass(frozen=True)
class ClusterSources:
    entity_mentions: tuple[ClusterEntityMention, ...]
    named_mentions: tuple[ClusterNamedMention, ...]
    facts: tuple[ClusterFact, ...]


@dataclass(frozen=True)
class ClusterNode:
    node_id: str
    node_type: str
    label: str
    reading_position: float
    mention_count: int


@dataclass(frozen=True)
class ClusterEdge:
    source_id: str
    target_id: str
    weight: float


@dataclass(frozen=True)
class ClusterGraph:
    book_id: str
    nodes: tuple[ClusterNode, ...]
    edges: tuple[ClusterEdge, ...]


@dataclass(frozen=True)
class Community:
    community_id: str
    parent_id: str | None
    level: int
    member_ids: tuple[str, ...]
    seed_node_id: str
    first_seen_position: float
    internal_weight: float
    signature_hash: str


@dataclass(frozen=True)
class CommunityTree:
    communities: tuple[Community, ...]
    node_count: int
    edge_count: int
    modularity: float | None
    algorithm: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class ClusterParameters:
    resolution: float
    max_levels: int
    min_size: int
    seed: int
    objective: ClusterObjective
    fact_edge_weight: float
    cooccurrence_edge_weight: float
    max_nodes_per_chunk: int = 50
    min_members: int = 2
