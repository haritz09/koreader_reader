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
from core.ports.llm_provider import (
    LLMConfigurationError,
    LLMPermanentError,
    LLMQuotaExhaustedError,
    LLMTransientError,
)

logger = logging.getLogger(__name__)

MAX_ALIASES = 8

_EXTRACTION_RULES = """\
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

Keep statements concise (under 200 words).\
"""

_SYSTEM_PROMPT = (
    """\
Given a chunk of text from a book, extract all entities, facts, events, and locations mentioned.

Return a JSON object with four arrays:
- "entities": objects with "name", "entity_type", optional "description", optional "sub_type", optional "aliases", optional "importance"
- "facts": objects with "statement", optional "subject", optional "object"
- "events": objects with "name", "description"
- "locations": objects with "name", optional "description"

"""
    + _EXTRACTION_RULES
    + """
Return ONLY valid JSON, no markdown.\
"""
)

_BATCH_SYSTEM_PROMPT = (
    """\
You will receive a JSON array of objects with "chunk_id" and "text".

For each object, extract all entities, facts, events, and locations mentioned in that text.
Return a JSON object with a "chunks" array. Each element must have:
- "chunk_id": the exact chunk_id from the input
- "entities": objects with "name", "entity_type", optional "description", optional "sub_type", optional "aliases", optional "importance"
- "facts": objects with "statement", optional "subject", optional "object"
- "events": objects with "name", "description"
- "locations": objects with "name", optional "description"

Every input chunk_id must appear exactly once. Do not use information from one chunk in another.

"""
    + _EXTRACTION_RULES
    + """
Return ONLY valid JSON, no markdown.\
"""
)

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

    @property
    def model(self) -> str:
        return self._model

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        content = await self._post_chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": chunk_text},
            ],
            0.1,
        )
        return self._parse_response(content)

    async def extract_knowledge_batch(
        self,
        chunks: list[tuple[str, str]],
    ) -> dict[str, KnowledgeExtractionResult]:
        if not chunks:
            return {}
        payload = [{"chunk_id": chunk_id, "text": text} for chunk_id, text in chunks]
        content = await self._post_chat(
            [
                {"role": "system", "content": _BATCH_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            0.1,
        )
        return self._parse_batch_response(content, {chunk_id for chunk_id, _ in chunks})

    async def resolve_group(
        self, candidates: Sequence[EntityCandidate]
    ) -> list[list[str]]:
        if len(candidates) < 2:
            return []

        listing = "\n".join(
            f"- id={c.entity_id} name={c.name!r} type={c.entity_type!r}" for c in candidates
        )
        content = await self._post_chat(
            [
                {"role": "system", "content": _RESOLUTION_PROMPT},
                {"role": "user", "content": listing},
            ],
            0.0,
        )
        return self._parse_resolution(content)

    async def _post_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> str:
        if not self._api_key:
            raise LLMConfigurationError("LLM API key is not configured")

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        try:
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
        except (httpx.TimeoutException, httpx.TransportError) as error:
            raise LLMTransientError(str(error)) from error

        self._raise_for_status(response)

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise LLMTransientError("LLM returned an invalid response") from error
        if not isinstance(content, str):
            raise LLMTransientError("LLM returned an invalid response")
        return content

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        detail = response.text[:300]
        if status in (401, 403, 404, 422):
            raise LLMConfigurationError(f"LLM configuration failed ({status})")
        if status == 429:
            daily, retry_after = _daily_quota(response)
            if daily:
                raise LLMQuotaExhaustedError(
                    f"LLM daily quota exhausted: {detail}",
                    retry_after,
                )
            raise LLMTransientError(
                f"LLM rate limit hit: {detail}",
                retry_after,
            )
        if status == 408 or status >= 500:
            raise LLMTransientError(
                f"LLM request failed ({status}): {detail}",
                _retry_after(response.headers.get("Retry-After")),
            )
        raise LLMPermanentError(f"LLM request failed ({status}): {detail}")

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
        except json.JSONDecodeError as error:
            raise LLMTransientError("LLM returned invalid JSON") from error

        if not isinstance(data, dict):
            raise LLMTransientError("LLM returned a non-object JSON payload")

        return _parse_payload(data)

    @staticmethod
    def _parse_batch_response(
        content: str,
        expected_ids: set[str],
    ) -> dict[str, KnowledgeExtractionResult]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMTransientError("LLM returned invalid JSON") from error

        if not isinstance(data, dict):
            raise LLMTransientError("LLM returned a non-object JSON payload")
        raw_chunks = data.get("chunks")
        if not isinstance(raw_chunks, list):
            raise LLMTransientError("LLM returned an invalid batch response")

        results: dict[str, KnowledgeExtractionResult] = {}
        for raw in raw_chunks:
            if not isinstance(raw, dict):
                raise LLMTransientError("LLM returned an invalid batch response")
            chunk_id = raw.get("chunk_id")
            if (
                not isinstance(chunk_id, str)
                or chunk_id not in expected_ids
                or chunk_id in results
            ):
                raise LLMTransientError("LLM returned an invalid batch response")
            results[chunk_id] = _parse_payload(raw)

        if set(results) != expected_ids:
            raise LLMTransientError("LLM returned an incomplete batch response")
        return results


def _parse_payload(data: dict) -> KnowledgeExtractionResult:
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

    return KnowledgeExtractionResult(
        entities=entities,
        facts=facts,
        events=events,
        locations=locations,
    )


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _parse_duration(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, str) and value.endswith("s"):
        try:
            return max(0.0, float(value[:-1]))
        except ValueError:
            return None
    return None


def _daily_quota(response: httpx.Response) -> tuple[bool, float | None]:
    header_delay = _retry_after(response.headers.get("Retry-After"))
    retry_after = header_delay
    daily = header_delay is not None and header_delay > 300

    try:
        body = response.json()
    except ValueError:
        return daily, retry_after
    if isinstance(body, list):
        body = body[0] if len(body) == 1 else None
    if not isinstance(body, dict):
        return daily, retry_after
    error = body.get("error")
    if isinstance(error, list):
        error = error[0] if len(error) == 1 else None
    if not isinstance(error, dict):
        return daily, retry_after

    code = str(error.get("code", "")).lower()
    error_type = str(error.get("type", "")).lower()
    if code in {"insufficient_quota", "quota_exceeded"}:
        daily = True
    if error_type in {"insufficient_quota", "quota_exceeded"}:
        daily = True
    message = str(error.get("message", "")).lower()
    if any(token in message for token in ("per day", "daily", "requests per day")):
        daily = True

    details = error.get("details")
    if not isinstance(details, list):
        if retry_after is not None and retry_after > 300:
            daily = True
        return daily, retry_after

    for detail in details:
        if not isinstance(detail, dict):
            continue
        detail_type = str(detail.get("@type", ""))
        if detail_type.endswith("RetryInfo"):
            parsed = _parse_duration(detail.get("retryDelay"))
            if parsed is not None:
                retry_after = parsed
        if not detail_type.endswith("QuotaFailure"):
            continue
        violations = detail.get("violations")
        if not isinstance(violations, list):
            continue
        for violation in violations:
            if not isinstance(violation, dict):
                continue
            quota_text = " ".join(
                str(violation.get(key, "")) for key in ("quotaId", "quotaMetric")
            ).lower()
            if (
                "perday" in quota_text
                or "per day" in quota_text
                or "daily" in quota_text
            ):
                daily = True

    if retry_after is not None and retry_after > 300:
        daily = True
    return daily, retry_after


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
