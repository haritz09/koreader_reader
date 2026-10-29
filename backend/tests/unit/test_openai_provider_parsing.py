import asyncio
import json

import httpx
import pytest

from adapters.llm.openai_provider import MAX_ALIASES, OpenAIProvider
from core.config import settings
from core.domain.entities.knowledge import ENTITY_TYPES, FALLBACK_ENTITY_TYPE
from core.ports.llm_provider import (
    LLMConfigurationError,
    LLMPermanentError,
    LLMQuotaExhaustedError,
    LLMTransientError,
)


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


def test_without_an_api_key_extraction_fails_as_configuration_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "")

    with pytest.raises(LLMConfigurationError):
        asyncio.run(OpenAIProvider().extract_knowledge("some chunk text"))


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


def test_a_malformed_or_non_object_payload_is_transient() -> None:
    for content in ("not json", "[1, 2, 3]", '"text"'):
        with pytest.raises(LLMTransientError):
            OpenAIProvider._parse_response(content)


def test_a_batch_response_keeps_each_chunk_separate() -> None:
    payload = {
        "chunks": [
            {"chunk_id": "c1", "entities": [entity()]},
            {"chunk_id": "c2", "facts": [{"statement": "A later fact."}]},
        ]
    }

    results = OpenAIProvider._parse_batch_response(
        json.dumps(payload),
        {"c1", "c2"},
    )

    assert results["c1"].entities[0].name == "Vin"
    assert results["c1"].facts == []
    assert results["c2"].entities == []
    assert results["c2"].facts[0].statement == "A later fact."


def test_a_batch_response_must_contain_every_expected_chunk_once() -> None:
    incomplete = {"chunks": [{"chunk_id": "c1"}]}
    duplicate = {
        "chunks": [
            {"chunk_id": "c1"},
            {"chunk_id": "c1"},
        ]
    }
    unknown = {"chunks": [{"chunk_id": "c1"}, {"chunk_id": "other"}]}

    for payload in (incomplete, duplicate, unknown):
        with pytest.raises(LLMTransientError):
            OpenAIProvider._parse_batch_response(
                json.dumps(payload),
                {"c1", "c2"},
            )


def test_a_per_day_quota_failure_is_not_treated_as_a_rate_limit() -> None:
    response = httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "message": "Quota exceeded.",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaId": (
                                    "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
                                )
                            }
                        ],
                    },
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "3600s",
                    },
                ],
            }
        },
        request=httpx.Request("POST", "https://example.test"),
    )

    with pytest.raises(LLMQuotaExhaustedError) as error:
        OpenAIProvider._raise_for_status(response)

    assert error.value.retry_after == 3600.0


def test_a_per_minute_quota_failure_stays_transient() -> None:
    response = httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "message": "Quota exceeded.",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaId": (
                                    "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
                                )
                            }
                        ],
                    },
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "30s",
                    },
                ],
            }
        },
        request=httpx.Request("POST", "https://example.test"),
    )

    with pytest.raises(LLMTransientError) as error:
        OpenAIProvider._raise_for_status(response)

    assert error.value.retry_after == 30.0


def test_a_long_retry_after_without_quota_details_is_daily_quota() -> None:
    response = httpx.Response(
        429,
        headers={"Retry-After": "7200"},
        request=httpx.Request("POST", "https://example.test"),
    )

    with pytest.raises(LLMQuotaExhaustedError) as error:
        OpenAIProvider._raise_for_status(response)

    assert error.value.retry_after == 7200.0


def test_auth_and_configuration_failures_abort_the_book() -> None:
    for status in (401, 403, 404, 422):
        response = httpx.Response(
            status,
            request=httpx.Request("POST", "https://example.test"),
        )

        with pytest.raises(LLMConfigurationError):
            OpenAIProvider._raise_for_status(response)


def test_rate_limits_and_server_errors_are_transient() -> None:
    response = httpx.Response(
        429,
        headers={"Retry-After": "7"},
        request=httpx.Request("POST", "https://example.test"),
    )

    with pytest.raises(LLMTransientError) as error:
        OpenAIProvider._raise_for_status(response)

    assert error.value.retry_after == 7.0

    for status in (408, 500, 503):
        with pytest.raises(LLMTransientError):
            OpenAIProvider._raise_for_status(
                httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
            )


def test_other_client_errors_are_permanent() -> None:
    with pytest.raises(LLMPermanentError):
        OpenAIProvider._raise_for_status(
            httpx.Response(400, request=httpx.Request("POST", "https://example.test"))
        )


def test_non_list_and_non_dict_rows_are_tolerated() -> None:
    result = parse({"entities": "nope", "facts": [1, None], "events": [{}], "locations": 7})

    assert result["entities"] == []
    assert result["facts"] == []
    assert result["events"] == []
    assert result["locations"] == []
