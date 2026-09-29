"""OpenAI-compatible LLM adapter."""

import json
import logging

import httpx

from core.config import settings
from core.domain.entities.knowledge import KnowledgeExtractionResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Given a chunk of text from a book, extract all entities, facts, events, and locations mentioned.

Return a JSON object with four arrays:
- "entities": objects with "name" and "entity_type" (character, place, concept, organization, other)
- "facts": objects with "statement", optional "subject", optional "object"
- "events": objects with "description"
- "locations": objects with "name", optional "description"

Keep statements concise (under 200 words). Return ONLY valid JSON, no markdown.\
"""


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or settings.llm_api_key
        self._model = model or settings.llm_model
        self._base_url = "https://api.openai.com/v1"

    async def extract_knowledge(self, chunk_text: str) -> KnowledgeExtractionResult:
        if not self._api_key:
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

    @staticmethod
    def _parse_response(content: str) -> KnowledgeExtractionResult:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON: %s", content[:200])
            return KnowledgeExtractionResult(entities=[], facts=[], events=[], locations=[])

        from core.domain.entities.knowledge import Entity, Event, Fact, Location
        from uuid import uuid4

        _uid = lambda: str(uuid4())

        entities = [
            Entity(entity_id=_uid(), book_id="", chunk_id="", name=e["name"], entity_type=e.get("entity_type", "other"), reading_position=0.0)
            for e in data.get("entities", [])
        ]
        facts = [
            Fact(fact_id=_uid(), book_id="", chunk_id="", statement=f["statement"], subject=f.get("subject"), object=f.get("object"), reading_position=0.0)
            for f in data.get("facts", [])
        ]
        events = [
            Event(event_id=_uid(), book_id="", chunk_id="", description=ev["description"], reading_position=0.0)
            for ev in data.get("events", [])
        ]
        locations = [
            Location(location_id=_uid(), book_id="", chunk_id="", name=loc["name"], description=loc.get("description"), reading_position=0.0)
            for loc in data.get("locations", [])
        ]

        return KnowledgeExtractionResult(entities=entities, facts=facts, events=events, locations=locations)
