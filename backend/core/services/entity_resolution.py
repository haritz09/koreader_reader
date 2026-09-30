"""Deterministic-first entity resolution with a language-model fallback.

Mentions of the same character are extracted independently per chunk, so
``entities`` rows carry no cross-chunk identity. This service assigns every
mention a ``canonical_id`` so the graph can merge them into a single node.
"""

import logging
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.domain.entities.graph import EntityCandidate, EntityResolution
from core.ports.entity_resolver import EntityResolver
from core.ports.knowledge_repository import KnowledgeRepository

logger = logging.getLogger(__name__)

DETERMINISTIC = "deterministic"
LLM = "llm"

_SIMILARITY_BUDGET = 0.34
_NAME_BUCKET_SIZE = 2
# Apostrophes are dropped rather than spaced out, so "O'Brien" and "Obrien"
# still normalize together. Treating them as separators would make a possessive
# look like a two-word name.
_APOSTROPHES = re.compile(r"['\u2019\u02bc]")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Casefold, drop combining marks and punctuation, and collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", name)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    deapostrophized = _APOSTROPHES.sub("", without_marks)
    cleaned = _PUNCTUATION.sub(" ", deapostrophized.casefold())
    return _WHITESPACE.sub(" ", cleaned).strip()


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def names_are_similar(left: str, right: str) -> bool:
    """True when two distinct normalized names are plausibly the same entity."""
    if left == right or not left or not right:
        return False
    longest = max(len(left), len(right))
    return _levenshtein(left, right) / longest <= _SIMILARITY_BUDGET


@dataclass(frozen=True)
class _Group:
    members: tuple[str, ...]
    method: str


class EntityResolutionService:
    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        entity_resolver: EntityResolver,
    ) -> None:
        self._repository = knowledge_repository
        self._resolver = entity_resolver

    async def resolve(self, book_id: str) -> EntityResolution:
        candidates = await self._repository.get_entity_candidates(book_id)
        if not candidates:
            return EntityResolution({}, {}, changed=False)

        by_id = {candidate.entity_id: candidate for candidate in candidates}
        groups: list[_Group] = self._deterministic_groups(candidates)
        for subset in self._ambiguous_subsets(candidates, groups):
            groups.extend(await self._escalate(subset))

        canonical_by_entity, method_by_entity = self._canonicalize(groups, by_id)
        changed = await self._has_changed(book_id, canonical_by_entity, method_by_entity)
        return EntityResolution(
            canonical_by_entity=canonical_by_entity,
            method_by_entity=method_by_entity,
            changed=changed,
        )

    @staticmethod
    def _deterministic_groups(candidates: Sequence[EntityCandidate]) -> list[_Group]:
        buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
        for candidate in candidates:
            key = (normalize_name(candidate.name), candidate.entity_type.strip().casefold())
            buckets[key].append(candidate.entity_id)
        return [_Group(tuple(members), DETERMINISTIC) for members in buckets.values()]

    @staticmethod
    def _ambiguous_subsets(
        candidates: Sequence[EntityCandidate],
        groups: Sequence[_Group],
    ) -> list[list[EntityCandidate]]:
        """Entity sets that exact name and type matching cannot settle.

        Two cases need a language model: the same name tagged with conflicting
        entity types, which usually means one extraction was wrong, and distinct
        names close enough to be an alias of each other.
        """
        by_id = {candidate.entity_id: candidate for candidate in candidates}
        settled: set[str] = set()
        for group in groups:
            if group.method == DETERMINISTIC and len(group.members) > 1:
                settled.update(group.members)

        subsets: list[list[EntityCandidate]] = []
        claimed: set[str] = set()

        by_normalized: dict[str, set[str]] = defaultdict(set)
        for candidate in candidates:
            if candidate.entity_id not in settled:
                by_normalized[normalize_name(candidate.name)].add(candidate.entity_id)
        for entity_ids in by_normalized.values():
            if len(entity_ids) > 1:
                subsets.append([by_id[entity_id] for entity_id in sorted(entity_ids)])
                claimed |= entity_ids

        buckets: dict[str, set[str]] = defaultdict(set)
        for candidate in candidates:
            if candidate.entity_id not in settled and candidate.entity_id not in claimed:
                buckets[normalize_name(candidate.name)[:_NAME_BUCKET_SIZE]].add(
                    candidate.entity_id
                )
        for entity_ids in buckets.values():
            ordered = sorted(entity_ids)
            names = {entity_id: normalize_name(by_id[entity_id].name) for entity_id in ordered}
            for index, left_id in enumerate(ordered):
                for right_id in ordered[index + 1 :]:
                    if names_are_similar(names[left_id], names[right_id]):
                        subsets.append([by_id[left_id], by_id[right_id]])
                        claimed |= {left_id, right_id}
        return subsets

    async def _escalate(self, subset: Sequence[EntityCandidate]) -> list[_Group]:
        if not subset:
            return []
        try:
            resolved = await self._resolver.resolve_group(list(subset))
        except Exception:
            logger.exception(
                "Entity resolver failed for %d candidates, keeping them separate",
                len(subset),
            )
            return [_Group((candidate.entity_id,), LLM) for candidate in subset]

        allowed = {candidate.entity_id for candidate in subset}
        groups: list[_Group] = []
        placed: set[str] = set()
        for group in resolved or ():
            members = tuple(sorted({e for e in group if e in allowed}))
            if not members:
                continue
            groups.append(_Group(members, LLM))
            placed.update(members)
        for candidate in subset:
            if candidate.entity_id not in placed:
                groups.append(_Group((candidate.entity_id,), LLM))
        return groups

    @staticmethod
    def _canonicalize(
        groups: Sequence[_Group],
        by_id: Mapping[str, EntityCandidate],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Point every member at the earliest mention of its group.

        Choosing the earliest mention keeps the mapping stable across runs. It
        stores an id rather than a name, so it cannot disclose a later alias.
        """
        canonical_by_entity: dict[str, str] = {}
        method_by_entity: dict[str, str] = {}
        for group in groups:
            if not group.members:
                continue
            canonical_id = min(
                group.members,
                key=lambda entity_id: (
                    by_id[entity_id].reading_position,
                    entity_id,
                ),
            )
            for entity_id in group.members:
                canonical_by_entity[entity_id] = canonical_id
                method_by_entity[entity_id] = group.method
        return canonical_by_entity, method_by_entity

    async def _has_changed(
        self,
        book_id: str,
        canonical_by_entity: Mapping[str, str],
        method_by_entity: Mapping[str, str],
    ) -> bool:
        stored = await self._repository.get_resolution(book_id)
        for entity_id, canonical_id in canonical_by_entity.items():
            stored_canonical, stored_method = stored.get(entity_id, (None, None))
            method = method_by_entity[entity_id]
            if stored_canonical != canonical_id or stored_method != method:
                return True
        return False
