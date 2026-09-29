"""Entities, events, facts and locations domain objects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    entity_id: str
    book_id: str
    chunk_id: str
    name: str
    entity_type: str
    reading_position: float


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
