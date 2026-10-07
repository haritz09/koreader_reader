import asyncio

import pytest

from core.domain.entities.graph import EntityMention, FactLink
from core.domain.entities.knowledge import EVENT_NODE_TYPE, LOCATION_NODE_TYPE
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
    description: str = "",
    sub_type: str | None = None,
    aliases: tuple[str, ...] = (),
    importance: int | None = None,
) -> EntityMention:
    return EntityMention(
        entity_id=entity_id,
        canonical_id=canonical_id or entity_id,
        name=name,
        entity_type=entity_type,
        reading_position=position,
        description=description,
        sub_type=sub_type,
        aliases=aliases,
        importance=importance,
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


def test_an_edge_appears_once_its_target_has_been_read() -> None:
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
            mention("l1", "Alice", 0.2, entity_type=LOCATION_NODE_TYPE),
            mention("e2", "Bob", 0.3),
        ],
        [fact("f1", "Alice", "Bob", 0.4)],
        1.0,
    )

    assert graph.edges == ()


def test_a_place_and_a_person_sharing_a_name_stay_separate_nodes() -> None:
    graph = build(
        [
            mention("e1", "Alice", 0.1, entity_type="character"),
            mention("l1", "Alice", 0.2, entity_type=LOCATION_NODE_TYPE),
        ],
        [],
        1.0,
    )

    assert [(node.node_id, node.node_type) for node in graph.nodes] == [
        ("e1", "character"),
        ("l1", LOCATION_NODE_TYPE),
    ]


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


def test_a_place_is_a_first_class_node_of_type_location() -> None:
    graph = build(
        [mention("l1", "Luthadel", 0.1, entity_type=LOCATION_NODE_TYPE)],
        [],
        1.0,
    )

    node = graph.nodes[0]
    assert node.node_type == LOCATION_NODE_TYPE
    assert node.label == "Luthadel"
    assert node.node_id == "l1"


def test_repeated_mentions_of_a_place_merge_into_one_node_by_name() -> None:
    graph = build(
        [
            mention("l2", "Capital", 0.7, entity_type=LOCATION_NODE_TYPE),
            mention("l1", "capital.", 0.2, entity_type=LOCATION_NODE_TYPE),
        ],
        [],
        1.0,
    )

    assert len(graph.nodes) == 1
    assert graph.nodes[0].node_id == "l1"
    assert graph.nodes[0].first_seen_position == 0.2
    assert graph.nodes[0].mention_count == 2


def test_an_event_is_a_first_class_node_of_type_event() -> None:
    graph = build(
        [
            mention(
                "ev1",
                "The Siege of Luthadel",
                0.4,
                entity_type=EVENT_NODE_TYPE,
                description="The city walls were breached at dawn.",
            ),
        ],
        [],
        1.0,
    )

    node = graph.nodes[0]
    assert node.node_type == EVENT_NODE_TYPE
    assert node.node_id == "ev1"
    assert node.description == "The city walls were breached at dawn."


def test_a_place_and_an_event_with_the_same_name_stay_separate_nodes() -> None:
    graph = build(
        [
            mention("l1", "Luthadel", 0.1, entity_type=LOCATION_NODE_TYPE),
            mention("ev1", "Luthadel", 0.2, entity_type=EVENT_NODE_TYPE),
        ],
        [],
        1.0,
    )

    assert sorted(node.node_type for node in graph.nodes) == [
        EVENT_NODE_TYPE,
        LOCATION_NODE_TYPE,
    ]


def test_an_event_can_be_the_endpoint_of_an_edge() -> None:
    graph = build(
        [
            mention("e1", "Vin", 0.1),
            mention("ev1", "The Siege", 0.2, entity_type=EVENT_NODE_TYPE),
        ],
        [fact("f1", "Vin", "The Siege", 0.3)],
        1.0,
    )

    assert [(edge.source_id, edge.target_id) for edge in graph.edges] == [
        ("e1", "ev1")
    ]


def test_a_node_description_comes_from_earliest_visible_mention() -> None:
    graph = build(
        [
            mention("e1", "Vin", 0.1, canonical_id="e1", description="A street urchin."),
            mention("e2", "Vin", 0.9, canonical_id="e1", description="The Last Emperor."),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].description == "A street urchin."


def test_a_later_description_cannot_describe_a_node_the_reader_has_not_reached() -> None:
    mentions = [
        mention("e1", "Vin", 0.1, canonical_id="e1"),
        mention("e2", "Vin", 0.9, canonical_id="e1", description="The Last Emperor."),
    ]

    assert build(mentions, [], 0.5).nodes[0].description == ""
    assert build(mentions, [], 1.0).nodes[0].description == "The Last Emperor."


def test_a_node_sub_type_comes_from_earliest_visible_mention() -> None:
    graph = build(
        [
            mention("e1", "Vin", 0.1, canonical_id="e1", sub_type=None),
            mention("e2", "Vin", 0.3, canonical_id="e1", sub_type="mistborn"),
            mention("e3", "Vin", 0.8, canonical_id="e1", sub_type="emperor"),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].sub_type == "mistborn"


def test_aliases_are_the_other_visible_names_without_repeating_the_label() -> None:
    graph = build(
        [
            mention("e1", "Vin", 0.1, canonical_id="e1"),
            mention("e2", "Vine", 0.2, canonical_id="e1"),
            mention("e3", "vin", 0.3, canonical_id="e1"),
            mention("e4", "The Last Emperor", 0.4, canonical_id="e1", aliases=("Reen's sister",)),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].aliases == ("Vine", "The Last Emperor", "Reen's sister")


def test_a_later_alias_cannot_reach_a_reader_at_an_earlier_position() -> None:
    mentions = [
        mention("e1", "Vin", 0.1, canonical_id="e1"),
        mention("e2", "The Last Emperor", 0.9, canonical_id="e1"),
    ]

    assert build(mentions, [], 0.5).nodes[0].aliases == ()
    assert build(mentions, [], 1.0).nodes[0].aliases == ("The Last Emperor",)


def test_entity_nodes_carry_no_alias_that_is_only_another_mention_of_the_name() -> None:
    graph = build(
        [
            mention("e1", "Luthadel", 0.1, canonical_id="e1"),
            mention("e2", "Luthadel", 0.2, canonical_id="e1"),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].aliases == ()


def test_entity_importance_comes_from_earliest_mention() -> None:
    graph = build(
        [
            mention("e1", "Alice", 0.1, canonical_id="e1", importance=3),
            mention("e2", "Alice", 0.6, canonical_id="e1", importance=2),
            mention("e3", "Alice", 0.9, canonical_id="e1", importance=1),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].importance == 1


def test_entity_importance_uses_minimum_visible_importance() -> None:
    """A node shows the highest importance encountered so far (smallest number)."""
    graph = build(
        [
            mention("e1", "Alice", 0.1, canonical_id="e1", importance=3),
            mention("e2", "Alice", 0.4, canonical_id="e1", importance=2),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].importance == 2


def test_entity_importance_is_none_when_not_set_on_any_mention() -> None:
    graph = build(
        [
            mention("e1", "Alice", 0.1, canonical_id="e1", importance=None),
            mention("e2", "Alice", 0.6, canonical_id="e1", importance=None),
        ],
        [],
        1.0,
    )

    assert graph.nodes[0].importance is None


def test_entity_importance_respects_reading_position() -> None:
    """The displayed importance never exceeds what the reader has reached."""
    mentions = [
        mention("e1", "Alice", 0.1, canonical_id="e1", importance=3),
        mention("e2", "Alice", 0.8, canonical_id="e1", importance=1),
    ]

    early = build(mentions, [], 0.5)
    late = build(mentions, [], 1.0)

    assert early.nodes[0].importance == 3
    assert late.nodes[0].importance == 1


def test_entity_importance_changing_as_reader_advances() -> None:
    """Importance rises (numerical value falls) progressively with reading."""
    at_02 = build(
        [
            mention("e1", "Alice", 0.1, canonical_id="e1", importance=3),
        ],
        [],
        0.2,
    )
    at_05 = build(
        [
            mention("e1", "Alice", 0.1, canonical_id="e1", importance=3),
            mention("e2", "Alice", 0.4, canonical_id="e1", importance=2),
        ],
        [],
        0.5,
    )
    at_10 = build(
        [
            mention("e1", "Alice", 0.1, canonical_id="e1", importance=3),
            mention("e2", "Alice", 0.4, canonical_id="e1", importance=2),
            mention("e3", "Alice", 0.9, canonical_id="e1", importance=1),
        ],
        [],
        1.0,
    )

    assert at_02.nodes[0].importance == 3
    assert at_05.nodes[0].importance == 2
    assert at_10.nodes[0].importance == 1
