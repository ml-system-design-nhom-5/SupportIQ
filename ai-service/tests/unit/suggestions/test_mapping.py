"""The request and the results map to and from the contract exactly (CON-08, CON-21)."""

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from supportiq_ai_service.generated import SuggestionRequest
from supportiq_ai_service.platform import RequestContractError
from supportiq_ai_service.platform.web import render_json
from supportiq_ai_service.suggestions.api.requests import suggestion_input
from supportiq_ai_service.suggestions.api.responses import analysis_body, draft_outcome_body
from supportiq_ai_service.suggestions.domain import (
    DraftOutcome,
    IntentName,
    MoneyAmount,
    OrderFacts,
    StaffIntent,
    SuggestionInput,
)
from tests.unit.suggestions.fakes import (
    EXAMPLE_ANALYSIS,
    EXAMPLE_DRAFT_READY,
    EXAMPLE_LLM_UNAVAILABLE,
)

EXAMPLES = Path(__file__).parents[4] / "contracts/examples"
FULL_REQUEST = {
    "message": "Where is my refund for [ORDER_ID_1]?",
    "as_of": "2026-11-05T09:30:00Z",
    "kb_version": "kb-sample-1",
    "intent_override": "refund_status",
    "order_context": {
        "order_status": "delivered",
        "placed_at": "2026-10-20T08:00:00Z",
        "order_total": {"amount_minor": 125000, "currency": "VND"},
        "refund_status": "under_review",
        "refund_requested_at": "2026-11-01T10:15:30.5Z",
    },
}


def parsed(body: Mapping[str, object]) -> SuggestionRequest:
    # As a request body arrives: JSON text, parsed strictly (platform.web.parse_json_body).
    return SuggestionRequest.model_validate_json(json.dumps(body), strict=True)


def example(name: str) -> object:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))["value"]


def test_a_full_request_maps_to_the_domain_request() -> None:
    body = parsed(FULL_REQUEST)

    assert suggestion_input(body) == SuggestionInput(
        message="Where is my refund for [ORDER_ID_1]?",
        as_of=datetime(2026, 11, 5, 9, 30, tzinfo=UTC),
        kb_version="kb-sample-1",
        intent_override=IntentName("refund_status"),
        order_facts=OrderFacts(
            order_status="delivered",
            placed_at=datetime(2026, 10, 20, 8, 0, tzinfo=UTC),
            order_total=MoneyAmount(amount_minor=125000, currency="VND"),
            refund_status="under_review",
            refund_requested_at=datetime(2026, 11, 1, 10, 15, 30, 500_000, tzinfo=UTC),
        ),
    )


def test_absent_optional_fields_stay_none() -> None:
    body = parsed({"message": "Hello", "as_of": "2026-11-05T09:30:00Z"})

    mapped = suggestion_input(body)

    assert (mapped.order_facts, mapped.kb_version, mapped.intent_override) == (None, None, None)


@pytest.mark.parametrize(
    ("field", "value", "location"),
    [
        ("as_of", "2026-11-05T09:30:00", "body.as_of"),
        ("as_of", "2026-11-05T16:30:00+07:00", "body.as_of"),
        (
            "order_context",
            {"delivered_at": "2026-11-05T09:30:00"},
            "body.order_context.delivered_at",
        ),
    ],
)
def test_a_timestamp_without_utc_is_rejected_at_its_location(
    field: str, value: object, location: str
) -> None:
    body = parsed(FULL_REQUEST | {field: value})

    with pytest.raises(RequestContractError) as raised:
        suggestion_input(body)

    assert raised.value.locations == (location,)


def test_the_analysis_is_the_contract_example() -> None:
    body = json.loads(render_json(analysis_body(EXAMPLE_ANALYSIS)))

    assert body == example("createAnalysis/draft.json")


def test_a_staff_intent_has_no_probability_and_no_band() -> None:
    staff_analysis = replace(
        EXAMPLE_ANALYSIS, intent=StaffIntent(label=IntentName("refund_status")), alternatives=()
    )

    body = json.loads(render_json(analysis_body(staff_analysis)))

    assert body["intent"] == {"source": "staff", "label": "refund_status"}
    assert body["alternatives"] == []


@pytest.mark.parametrize(
    ("outcome", "example_name"),
    [
        (EXAMPLE_DRAFT_READY, "createDraft/draft-ready.json"),
        (EXAMPLE_LLM_UNAVAILABLE, "createDraft/llm-unavailable.json"),
    ],
)
def test_a_draft_outcome_is_its_contract_example(outcome: DraftOutcome, example_name: str) -> None:
    body = json.loads(render_json(draft_outcome_body(outcome)))

    assert body == example(example_name)
