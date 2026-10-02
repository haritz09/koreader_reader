import asyncio

import pytest

from core.domain.entities.graph import EntityMention, FactLink
from core.domain.value_objects.reading_position import InvalidReadingPositionError
from core.services.graph_assembly import GraphAssemblyService


class StubGraphRepository:
    def __init__(
        self,
        mentions: list[EntityMention],
        facts: list[FactLink],
        revision: int = 1,
    ) -> None:
        self.mentions = mentions
        self.facts = facts
        self.revision = revision
        self.requested_positions: list[float] = []

    async def get_visible_mentions(
        self, book_id: str, reading_position: float
    ) -> list[EntityMention]:
        self.requested_positions.append(reading_position)
        return [m for m in self.mentions if m.reading_position <= reading_position]

    async def get_visible_facts(
        self, book_id: str, reading_position: float
    ) -> list[FactLink]:
        return [f for f in self.facts if f.reading_position <= reading_position]

    async def get_revision(self, book_id: str) -> int:
        return self.revision

    async def delete_by_book(self, book_id: str) -> None:
        raise NotImplementedError


def mention(
    entity_id: str,
    name: str,
    position: float,
    canonical_id: str | None = None,
    entity_type: str = "character",
) -> EntityMention:
    return EntityMention(
        entity_id=entity_id,
        canonical_id=canonical_id or entity_id,
        name=name,
        entity_type=entity_type,
        reading_position=position,
    )


def fact(
    fact_id: str,
    subject: str | None,
    object_: str | None,
    position: float,
    chunk_id: str = "chunk-0",
) -> FactLink:
    return FactLink(
        fact_id=fact_id,
        chunk_id=chunk_id,
        statement=f"fact {fact_id}",
        subject=subject,
        object=object_,
        reading_position=position,
    )


def build(
    mentions: list[EntityMention],
    facts: list[FactLink],
    position: float,
    revision: int = 1,
):
    repository = StubGraphRepository(mentions, facts, revision)
    return asyncio.run(GraphAssemblyService(repository).build("book-1", position))


def test_mentions_sharing_a_canonical_id_merge_into_one_node() -> None:
    graph = build(
        [
            mention("e1", "Alice", 0.1, canonical_id="e1"),
            mention("e2", "Alice", 0.6, canonical_id="e1"),
        ],
        [],
        1.0,
    )

    assert len(graph.nodes) == 1
    assert graph.nodes[0].node_id == "e1"
    assert graph.nodes[0].mention_count == 2


def test_a_node_label_comes_from_the_earliest_visible_mention() -> None:
    graph = build(
        [
            mention("e1", "Alice Drake", 0.2, canonical_id="e1"),
            mention("e2", "Lady Drake", 0.8, canonical_id="e1"),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].label == "Alice Drake"
    assert graph.nodes[0].first_seen_position == 0.2


def test_a_later_alias_cannot_label_a_node_the_reader_has_not_reached() -> None:
    mentions = [
        mention("e1", "Alice Drake", 0.2, canonical_id="e1"),
        mention("e2", "The Ice Queen", 0.85, canonical_id="e1"),
    ]

    at_early_position = build(mentions, [], 0.5)
    at_late_position = build(mentions, [], 1.0)

    assert at_early_position.nodes[0].label == "Alice Drake"
    assert at_early_position.nodes[0].mention_count == 1
    assert at_late_position.nodes[0].label == "Alice Drake"
    assert at_late_position.nodes[0].mention_count == 2


def test_mentions_beyond_the_current_position_produce_no_node() -> None:
    graph = build(
        [
            mention("e1", "Alice", 0.1),
            mention("e2", "The Ice Queen", 0.85),
        ],
        [],
        0.5,
    )

    assert [node.label for node in graph.nodes] == ["Alice"]


def test_rewinding_shrinks_the_graph() -> None:
    mentions = [
        mention("e1", "Alice", 0.1),
        mention("e2", "The Ice Queen", 0.85),
    ]

    forward = build(mentions, [], 1.0)
    rewound = build(mentions, [], 0.5)

    assert len(forward.nodes) == 2
    assert len(rewound.nodes) == 1


def test_a_fact_becomes_an_edge_between_visible_nodes() -> None:
    graph = build(
        [mention("e1", "Alice", 0.1), mention("e2", "Bob", 0.2)],
        [fact("f1", "Alice", "Bob", 0.3)],
        1.0,
    )

    assert len(graph.edges) == 1
    assert graph.edges[0].source_id == "e1"
    assert graph.edges[0].target_id == "e2"
    assert graph.edges[0].edge_id == "f1"
    assert graph.edges[0].chunk_id == "chunk-0"


def test_an_edge_is_dropped_when_its_target_is_not_yet_visible() -> None:
    graph = build(
        [mention("e1", "Alice", 0.1), mention("e2", "Bob", 0.7)],
        [fact("f1", "Alice", "Bob", 0.3)],
        0.5,
    )

    assert graph.edges == ()


def test_an_edge_is_dropped_when_its_target_appears_after_the_fact() -> None:
    graph = build(
        [mention("e1", "Alice", 0.1), mention("e2", "Bob", 0.7)],
        [fact("f1", "Alice", "Bob", 0.3)],
        0.9,
    )

    assert len(graph.edges) == 1


def test_fact_endpoints_match_mentions_regardless_of_casing() -> None:
    graph = build(
        [mention("e1", "Alice Drake", 0.1), mention("e2", "Bob", 0.2)],
        [fact("f1", "alice drake", "BOB", 0.3)],
        1.0,
    )

    assert len(graph.edges) == 1


def test_an_edge_is_dropped_when_a_name_is_ambiguous_among_visible_nodes() -> None:
    graph = build(
        [
            mention("e1", "Alice", 0.1, entity_type="character"),
            mention("e2", "Alice", 0.2, entity_type="place"),
            mention("e3", "Bob", 0.3),
        ],
        [fact("f1", "Alice", "Bob", 0.4)],
        1.0,
    )

    assert graph.edges == ()


def test_a_single_sided_fact_produces_no_edge() -> None:
    graph = build(
        [mention("e1", "Alice", 0.1), mention("e2", "Bob", 0.2)],
        [fact("f1", "Alice", None, 0.3)],
        1.0,
    )

    assert graph.edges == ()


def test_a_self_referential_fact_produces_no_edge() -> None:
    graph = build(
        [mention("e1", "Alice", 0.1)],
        [fact("f1", "Alice", "Alice", 0.3)],
        1.0,
    )

    assert graph.edges == ()


def test_nodes_are_ordered_by_first_appearance() -> None:
    graph = build(
        [
            mention("e2", "Bob", 0.6),
            mention("e1", "Alice", 0.1),
            mention("e3", "Carol", 0.3),
        ],
        [],
        1.0,
    )

    assert [node.label for node in graph.nodes] == ["Alice", "Carol", "Bob"]


def test_the_graph_reports_the_revision_and_position_it_was_built_at() -> None:
    graph = build([mention("e1", "Alice", 0.1)], [], 0.4, revision=7)

    assert graph.revision == 7
    assert graph.position == 0.4
    assert graph.book_id == "book-1"


def test_an_unread_book_yields_an_empty_graph_rather_than_everything() -> None:
    graph = build(
        [mention("e1", "Alice", 0.1), mention("e2", "Bob", 0.2)],
        [fact("f1", "Alice", "Bob", 0.3)],
        0.0,
    )

    assert graph.nodes == ()
    assert graph.edges == ()


@pytest.mark.parametrize("position", [1.0001, -0.5, float("nan")])
def test_an_out_of_range_position_fails_closed(position: float) -> None:
    repository = StubGraphRepository([], [])

    with pytest.raises(InvalidReadingPositionError):
        asyncio.run(GraphAssemblyService(repository).build("book-1", position))
