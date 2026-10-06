import asyncio
from collections.abc import Mapping, Sequence

from core.domain.entities.graph import EntityCandidate
from core.services.entity_resolution import (
    DETERMINISTIC,
    LLM,
    EntityResolutionService,
)


class StubResolver:
    """Records every escalation and replies with a fixed grouping."""

    def __init__(self, groups: Sequence[Sequence[str]] = ()) -> None:
        self._groups = list(groups)
        self.calls: list[list[EntityCandidate]] = []

    async def resolve_group(
        self, candidates: Sequence[EntityCandidate]
    ) -> list[list[str]]:
        self.calls.append(list(candidates))
        return [list(group) for group in self._groups]


class FailingResolver:
    async def resolve_group(
        self, candidates: Sequence[EntityCandidate]
    ) -> list[list[str]]:
        raise RuntimeError("resolver unavailable")


class StubKnowledgeRepository:
    def __init__(
        self,
        candidates: Sequence[EntityCandidate],
        stored: Mapping[str, tuple[str | None, str | None]] | None = None,
    ) -> None:
        self.candidates = list(candidates)
        self.stored = dict(stored or {})
        self.applied: list[Mapping[str, str]] = []

    async def get_entity_candidates(self, book_id: str) -> list[EntityCandidate]:
        return list(self.candidates)

    async def get_resolution(
        self, book_id: str
    ) -> Mapping[str, tuple[str | None, str | None]]:
        return dict(self.stored)

    async def apply_resolution(
        self,
        book_id: str,
        canonical_by_entity: Mapping[str, str],
        method_by_entity: Mapping[str, str],
    ) -> None:
        self.applied.append(dict(canonical_by_entity))


def candidate(
    entity_id: str,
    name: str,
    entity_type: str = "character",
    reading_position: float = 0.0,
) -> EntityCandidate:
    return EntityCandidate(
        entity_id=entity_id,
        name=name,
        entity_type=entity_type,
        reading_position=reading_position,
    )


def resolve(
    candidates: Sequence[EntityCandidate],
    resolver=None,
    stored: Mapping[str, tuple[str | None, str | None]] | None = None,
):
    repository = StubKnowledgeRepository(candidates, stored)
    service = EntityResolutionService(repository, resolver or StubResolver())
    return asyncio.run(service.resolve("book-1")), repository


def test_identical_names_in_different_chunks_become_one_identity() -> None:
    result, _ = resolve(
        [
            candidate("e1", "Alice Drake", reading_position=0.1),
            candidate("e2", "alice drake", reading_position=0.6),
        ]
    )

    assert result.canonical_by_entity == {"e1": "e1", "e2": "e1"}
    assert result.method_by_entity == {"e1": DETERMINISTIC, "e2": DETERMINISTIC}


def test_name_punctuation_and_apostrophes_are_folded() -> None:
    result, _ = resolve(
        [
            candidate("e1", "Dr. Alice O'Brien"),
            candidate("e2", "dr alice obrien"),
        ]
    )

    assert result.canonical_by_entity == {"e1": "e1", "e2": "e1"}
    assert set(result.method_by_entity.values()) == {DETERMINISTIC}


def test_distinct_names_stay_separate_without_escalation() -> None:
    resolver = StubResolver()

    result, _ = resolve(
        [
            candidate("e1", "Alice Drake"),
            candidate("e2", "Bartholomew Cube"),
        ],
        resolver=resolver,
    )

    assert result.canonical_by_entity == {"e1": "e1", "e2": "e2"}
    assert resolver.calls == []


def test_the_same_name_with_conflicting_types_is_escalated() -> None:
    resolver = StubResolver(groups=[["e1", "e2"]])

    result, _ = resolve(
        [
            candidate("e1", "Ash", entity_type="character"),
            candidate("e2", "Ash", entity_type="artifact"),
        ],
        resolver=resolver,
    )

    assert len(resolver.calls) == 1
    assert result.canonical_by_entity == {"e1": "e1", "e2": "e1"}
    assert set(result.method_by_entity.values()) == {LLM}


def test_near_duplicate_names_are_escalated() -> None:
    resolver = StubResolver(groups=[["e1", "e2"]])

    result, _ = resolve(
        [candidate("e1", "Alice"), candidate("e2", "Alicia")],
        resolver=resolver,
    )

    assert len(resolver.calls) == 1
    assert result.canonical_by_entity["e2"] == "e1"


def test_the_earliest_mention_becomes_the_canonical_identity() -> None:
    result, _ = resolve(
        [
            candidate("e1", "Alice", reading_position=0.7),
            candidate("e2", "Alicia", reading_position=0.2),
        ],
        resolver=StubResolver(groups=[["e1", "e2"]]),
    )

    assert result.canonical_by_entity == {"e1": "e2", "e2": "e2"}


def test_a_failing_resolver_keeps_candidates_separate() -> None:
    result, _ = resolve(
        [candidate("e1", "Alice"), candidate("e2", "Alicia")],
        resolver=FailingResolver(),
    )

    assert result.canonical_by_entity == {"e1": "e1", "e2": "e2"}


def test_unknown_ids_from_the_resolver_are_discarded() -> None:
    result, _ = resolve(
        [candidate("e1", "Alice"), candidate("e2", "Alicia")],
        resolver=StubResolver(groups=[["e1", "e2", "ghost"]]),
    )

    assert set(result.canonical_by_entity) == {"e1", "e2"}


def test_a_candidate_omitted_by_the_resolver_is_not_dropped() -> None:
    result, _ = resolve(
        [candidate("e1", "Alice"), candidate("e2", "Alicia")],
        resolver=StubResolver(groups=[["e1"]]),
    )

    assert result.canonical_by_entity == {"e1": "e1", "e2": "e2"}


def test_a_matching_stored_resolution_reports_no_change() -> None:
    candidates = [candidate("e1", "Alice"), candidate("e2", "Bob")]

    result, _ = resolve(
        candidates,
        stored={"e1": ("e1", DETERMINISTIC), "e2": ("e2", DETERMINISTIC)},
    )

    assert result.changed is False


def test_a_differing_stored_resolution_reports_a_change() -> None:
    candidates = [candidate("e1", "Alice"), candidate("e2", "Bob")]

    result, _ = resolve(
        candidates,
        stored={"e1": ("e2", DETERMINISTIC), "e2": ("e2", DETERMINISTIC)},
    )

    assert result.changed is True


def test_a_book_without_mentions_resolves_to_nothing() -> None:
    result, _ = resolve([])

    assert result.canonical_by_entity == {}
    assert result.changed is False
