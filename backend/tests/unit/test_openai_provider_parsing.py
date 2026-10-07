import asyncio
import json

from adapters.llm.openai_provider import MAX_ALIASES, OpenAIProvider
from core.config import settings
from core.domain.entities.knowledge import ENTITY_TYPES, FALLBACK_ENTITY_TYPE


def parse(payload: dict) -> dict:
    result = OpenAIProvider._parse_response(json.dumps(payload))
    return {
        "entities": result.entities,
        "facts": result.facts,
        "events": result.events,
        "locations": result.locations,
    }


def entity(**overrides) -> dict:
    return {"name": "Vin", "entity_type": "character", **overrides}


def test_without_an_api_key_no_knowledge_is_extracted(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "")

    result = asyncio.run(OpenAIProvider().extract_knowledge("some chunk text"))

    assert (result.entities, result.facts, result.events, result.locations) == (
        [],
        [],
        [],
        [],
    )


def test_entity_type_is_kept_when_it_belongs_to_the_vocabulary() -> None:
    for value in sorted(ENTITY_TYPES):
        result = parse({"entities": [entity(entity_type=value)]})

        assert result["entities"][0].entity_type == value


def test_an_unknown_entity_type_falls_back_to_other() -> None:
    result = parse({"entities": [entity(entity_type="place")], "facts": []})

    assert result["entities"][0].entity_type == FALLBACK_ENTITY_TYPE


def test_a_missing_or_blank_entity_type_falls_back_to_other() -> None:
    assert parse({"entities": [entity(entity_type=None)]})["entities"][0].entity_type == (
        FALLBACK_ENTITY_TYPE
    )
    assert parse({"entities": [entity(entity_type="  ")]})["entities"][0].entity_type == (
        FALLBACK_ENTITY_TYPE
    )


def test_entity_description_sub_type_and_aliases_are_parsed() -> None:
    result = parse(
        {
            "entities": [
                entity(
                    description="  A skaa street urchin. ",
                    sub_type=" mistborn ",
                    aliases=["Vine", "Reen's sister"],
                )
            ]
        }
    )

    parsed = result["entities"][0]
    assert parsed.description == "A skaa street urchin."
    assert parsed.sub_type == "mistborn"
    assert parsed.aliases == ("Vine", "Reen's sister")


def test_entity_importance_is_parsed() -> None:
    result = parse({"entities": [entity(importance=1)]})
    assert result["entities"][0].importance == 1

    result = parse({"entities": [entity(importance=2)]})
    assert result["entities"][0].importance == 2

    result = parse({"entities": [entity(importance=3)]})
    assert result["entities"][0].importance == 3


def test_entity_importance_is_none_when_missing_or_invalid() -> None:
    result = parse({"entities": [entity()]})
    assert result["entities"][0].importance is None

    result = parse({"entities": [entity(importance=0)]})
    assert result["entities"][0].importance is None

    result = parse({"entities": [entity(importance=4)]})
    assert result["entities"][0].importance is None

    result = parse({"entities": [entity(importance="high")]})
    assert result["entities"][0].importance is None


def test_aliases_drop_the_name_itself_duplicates_and_blanks() -> None:
    result = parse(
        {
            "entities": [
                entity(aliases=["vin", "VIN", "  ", "Vine", "Vine"])
            ]
        }
    )

    assert result["entities"][0].aliases == ("Vine",)


def test_aliases_are_capped_at_the_documented_limit() -> None:
    aliases = [f"alias-{index}" for index in range(MAX_ALIASES + 5)]

    result = parse({"entities": [entity(aliases=aliases)]})

    assert len(result["entities"][0].aliases) == MAX_ALIASES


def test_a_non_list_aliases_value_is_ignored() -> None:
    assert parse({"entities": [entity(aliases="Vine")]})["entities"][0].aliases == ()


def test_an_event_keeps_its_name_and_description_only() -> None:
    result = parse(
        {
            "events": [
                {
                    "name": "The Siege of Luthadel",
                    "description": "The walls were breached at dawn.",
                    "subject": "Vin",
                    "object": "the empire",
                }
            ]
        }
    )

    parsed = result["events"][0]
    assert parsed.name == "The Siege of Luthadel"
    assert parsed.description == "The walls were breached at dawn."
    assert not hasattr(parsed, "subject")
    assert not hasattr(parsed, "object")


def test_an_event_without_a_name_is_skipped() -> None:
    result = parse({"events": [{"description": "Something happened"}, {"name": "  "}]})

    assert result["events"] == []


def test_a_row_without_a_name_or_statement_is_skipped() -> None:
    result = parse(
        {
            "entities": [{"entity_type": "character"}, {"name": "   "}],
            "facts": [{"subject": "Vin"}, {"statement": " "}],
            "locations": [{"description": "A city"}],
        }
    )

    assert result["entities"] == []
    assert result["facts"] == []
    assert result["locations"] == []


def test_a_fact_without_subject_and_object_still_survives() -> None:
    result = parse({"facts": [{"statement": "The Lord Ruler fell."}]})

    parsed = result["facts"][0]
    assert parsed.subject is None
    assert parsed.object is None


def test_a_malformed_or_non_object_payload_yields_nothing() -> None:
    assert OpenAIProvider._parse_response("not json").entities == []
    assert OpenAIProvider._parse_response("[1, 2, 3]").facts == []
    assert OpenAIProvider._parse_response('"text"').events == []


def test_non_list_and_non_dict_rows_are_tolerated() -> None:
    result = parse({"entities": "nope", "facts": [1, None], "events": [{}], "locations": 7})

    assert result["entities"] == []
    assert result["facts"] == []
    assert result["events"] == []
    assert result["locations"] == []
