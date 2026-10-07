"""OpenAI-compatible LLM adapter."""

import json
import logging
from collections.abc import Sequence
from typing import cast
from uuid import uuid4

import httpx

from core.config import settings
from core.domain.entities.graph import EntityCandidate
from core.domain.entities.knowledge import (
    ENTITY_TYPES,
    FALLBACK_ENTITY_TYPE,
    Entity,
    EntityType,
    Event,
    Fact,
    KnowledgeExtractionResult,
    Location,
)

logger = logging.getLogger(__name__)

MAX_ALIASES = 8

_SYSTEM_PROMPT = """\
Given a chunk of text from a book, extract all entities, facts, events, and locations mentioned.

Return a JSON object with four arrays:
- "entities": objects with "name", "entity_type", optional "description", optional "sub_type", optional "aliases", optional "importance"
- "facts": objects with "statement", optional "subject", optional "object"
- "events": objects with "name", "description"
- "locations": objects with "name", optional "description"

"entity_type" MUST be exactly one of: character, enemy, artifact, organization, concept.
- character: a good or neutral person
- enemy: a hostile, villainous, or opposing person
- artifact: a physical object of significance, such as a weapon, ring, or relic
- organization: a faction, group, order, or institution
- concept: a body of knowledge, power system, law, or abstract idea

"sub_type" is an optional narrower kind or trait, such as mistborn, feruchemist, or sword.
"aliases" is an optional list of other names or titles the same entity is called in
this passage, copied exactly as written.
"importance" is an optional importance level from 1 (protagonist) to 3 (tertiary).

An event is a significant occurrence such as a battle. It stands on its own, so give
it a short "name" and its "description"; do not give it a subject or an object.

Keep statements concise (under 200 words). Return ONLY valid JSON, no markdown.\
"""

_RESOLUTION_PROMPT = """\
You are given name variants of entities extracted from a book, along with the \
type each was tagged with.

Decide which variants refer to the same real entity within this book. Different \
people who share a surname are NOT the same entity. A place and a person that \
happen to share a name are NOT the same entity.

Return ONLY valid JSON of the form {"groups": [["id1", "id2"], ["id3"]]} where \
every input id appears in exactly one group.\
"""


class OpenAIProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.llm_api_key
        self._model = model or settings.llm_model
        self._base_url = (base_url or settings.llm_base_url).rstrip("/")

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        if not self._api_key:
            logger.warning(
                "No LLM API key configured; knowledge extraction returns no results"
            )
            return KnowledgeExtractionResult(entities=[], facts=[], events=[], locations=[])

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": chunk_text},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        return self._parse_response(content)

    async def resolve_group(
        self, candidates: Sequence[EntityCandidate]
    ) -> list[list[str]]:
        if not self._api_key:
            logger.warning("No LLM API key configured; entity aliases stay unresolved")
            return []
        if len(candidates) < 2:
            return []

        listing = "\n".join(
            f"- id={c.entity_id} name={c.name!r} type={c.entity_type!r}" for c in candidates
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _RESOLUTION_PROMPT},
                {"role": "user", "content": listing},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        return self._parse_resolution(content)

    @staticmethod
    def _parse_resolution(content: str) -> list[list[str]]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Entity resolver returned invalid JSON: %s", content[:200])
            return []
        groups = data.get("groups")
        if not isinstance(groups, list):
            logger.warning("Entity resolver response has no groups array")
            return []
        return [
            [str(member) for member in group if isinstance(member, str)]
            for group in groups
            if isinstance(group, list)
        ]

    @staticmethod
    def _parse_response(content: str) -> KnowledgeExtractionResult:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON: %s", content[:200])
            return KnowledgeExtractionResult(entities=[], facts=[], events=[], locations=[])

        if not isinstance(data, dict):
            logger.warning("LLM returned a non-object JSON payload: %s", content[:200])
            return KnowledgeExtractionResult(entities=[], facts=[], events=[], locations=[])

        entities: list[Entity] = []
        for raw in _list_of(data.get("entities")):
            name = _text(raw.get("name"))
            if not name:
                continue
            entities.append(
                Entity(
                    entity_id=_uid(),
                    book_id="",
                    chunk_id="",
                    name=name,
                    entity_type=_entity_type(raw.get("entity_type")),
                    reading_position=0.0,
                    description=_text(raw.get("description")),
                    sub_type=_text(raw.get("sub_type")) or None,
                    aliases=_aliases(raw.get("aliases"), name),
                    importance=_importance(raw.get("importance")),
                )
            )

        facts: list[Fact] = []
        for raw in _list_of(data.get("facts")):
            statement = _text(raw.get("statement"))
            if not statement:
                continue
            facts.append(
                Fact(
                    fact_id=_uid(),
                    book_id="",
                    chunk_id="",
                    statement=statement,
                    subject=_optional_text(raw.get("subject")),
                    object=_optional_text(raw.get("object")),
                    reading_position=0.0,
                )
            )

        events: list[Event] = []
        for raw in _list_of(data.get("events")):
            name = _text(raw.get("name"))
            if not name:
                logger.warning("LLM returned an event without a name, skipping it")
                continue
            events.append(
                Event(
                    event_id=_uid(),
                    book_id="",
                    chunk_id="",
                    description=_text(raw.get("description")),
                    reading_position=0.0,
                    name=name,
                )
            )

        locations: list[Location] = []
        for raw in _list_of(data.get("locations")):
            name = _text(raw.get("name"))
            if not name:
                continue
            locations.append(
                Location(
                    location_id=_uid(),
                    book_id="",
                    chunk_id="",
                    name=name,
                    description=_optional_text(raw.get("description")),
                    reading_position=0.0,
                )
            )

        return KnowledgeExtractionResult(entities=entities, facts=facts, events=events, locations=locations)


def _uid() -> str:
    return str(uuid4())


def _list_of(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    return _text(value) or None


def _entity_type(value: object) -> EntityType:
    if isinstance(value, str):
        candidate = value.strip().casefold()
        if candidate in ENTITY_TYPES:
            return cast(EntityType, candidate)
    logger.warning("LLM returned an unknown entity_type %r, storing %r", value, FALLBACK_ENTITY_TYPE)
    return FALLBACK_ENTITY_TYPE


def _importance(value: object) -> int | None:
    if isinstance(value, int) and 1 <= value <= 3:
        return value
    return None


def _aliases(value: object, name: str) -> tuple[str, ...]:
    """Keep a short, order-preserving set of aliases that are not the name itself."""
    if not isinstance(value, list):
        return ()
    seen: set[str] = {_key(name)}
    aliases: list[str] = []
    for item in value:
        alias = _text(item)
        if not alias:
            continue
        key = _key(alias)
        if key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
        if len(aliases) >= MAX_ALIASES:
            break
    return tuple(aliases)


def _key(value: str) -> str:
    return " ".join(value.split()).casefold()
