"""Entities, events, facts and locations domain objects."""

from dataclasses import dataclass
from typing import Literal, get_args

EntityType = Literal[
    "character",
    "enemy",
    "artifact",
    "organization",
    "concept",
    "other",
]

# What the extraction prompt is asked for. Kept separate from ENTITY_TYPES so
# the fallback can never be requested from the model.
EXTRACTABLE_ENTITY_TYPES: tuple[str, ...] = (
    "character",
    "enemy",
    "artifact",
    "organization",
    "concept",
)

ENTITY_TYPES: frozenset[str] = frozenset(get_args(EntityType))

FALLBACK_ENTITY_TYPE: Literal["other"] = "other"

# A node can also be a place or an occurrence, which live in `locations` and
# `events` rather than in `entities`. These are part of the graph's node_type
# vocabulary and deliberately not part of entity_type.
LOCATION_NODE_TYPE: Literal["location"] = "location"
EVENT_NODE_TYPE: Literal["event"] = "event"

@dataclass(frozen=True)
class Entity:
    entity_id: str
    book_id: str
    chunk_id: str
    name: str
    entity_type: EntityType
    reading_position: float
    description: str = ""
    sub_type: str | None = None
    aliases: tuple[str, ...] = ()

@dataclass(frozen=True)
class Fact:
    fact_id: str
    book_id: str
    chunk_id: str
    statement: str
    subject: str | None
    object: str | None
    reading_position: float


@dataclass(frozen=True)
class Event:
    event_id: str
    book_id: str
    chunk_id: str
    description: str
    reading_position: float
    name: str = ""


@dataclass(frozen=True)
class Location:
    location_id: str
    book_id: str
    chunk_id: str
    name: str
    description: str | None
    reading_position: float


@dataclass
class KnowledgeExtractionResult:
    entities: list[Entity]
    facts: list[Fact]
    events: list[Event]
    locations: list[Location]
