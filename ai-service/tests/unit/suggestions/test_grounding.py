"""A draft is shown only when each statement cites a source of the right kind (TEST-26)."""

import dataclasses

import pytest

from app.drafting import DraftRequest, OrderFact, TokenUsage, WrittenDraft
from app.suggestions.domain import (
    DraftSegment,
    KbDocumentCitation,
    OrderContextCitation,
    OrderFieldName,
)
from app.suggestions.domain.grounding import (
    GROUNDING_FAILED,
    LLM_INVALID_OUTPUT,
    MAX_DRAFT_CHARS,
    DraftCheckError,
    check_draft,
)
from tests.unit.drafting.fakes import REQUEST

MAX_CHARS = 40
REFUND_FACT = OrderFact(source_id="S3", field="refund_status", value="approved")
FULL_REQUEST = dataclasses.replace(REQUEST, order_facts=(*REQUEST.order_facts, REFUND_FACT))


def _written(text: str, *cited: str, clarification: bool = False) -> WrittenDraft:
    return WrittenDraft(
        text=text, cited_source_ids=cited, is_clarification=clarification, usage=TokenUsage(1, 1)
    )


def _rejection(written: WrittenDraft, request: DraftRequest = FULL_REQUEST) -> str:
    with pytest.raises(DraftCheckError) as raised:
        check_draft(written, request, MAX_CHARS)
    return raised.value.reason_code


def test_a_grounded_draft_becomes_segments_with_their_citations() -> None:
    written = _written(
        "Hello!\n\nDeliveries take a few days [S1]. Your parcel is in_transit [S2].",
        "S1",
        "S2",
    )

    draft = check_draft(written, FULL_REQUEST, MAX_CHARS)

    assert draft.segments == (
        DraftSegment("segment-1", 0, "Hello!", ()),
        DraftSegment(
            "segment-2",
            1,
            "Deliveries take a few days. Your parcel is in_transit.",
            ("S1", "S2"),
        ),
    )
    assert draft.citations == (
        KbDocumentCitation("S1", "SAMPLE-DELIVERY-001", "1.0", "A fake passage about deliveries."),
        OrderContextCitation("S2", OrderFieldName("shipment_status")),
    )


def test_a_placeholder_that_the_message_does_not_hold_is_invalid_output() -> None:
    written = _written("Your order [ORDER_ID_2] is in_transit [S2].", "S2")

    assert _rejection(written) == LLM_INVALID_OUTPUT


def test_a_placeholder_of_the_message_may_stay() -> None:
    written = _written("Your order [ORDER_ID_1] is in_transit [S2].", "S2")

    assert (
        check_draft(written, FULL_REQUEST, MAX_CHARS)
        .segments[0]
        .text.startswith("Your order [ORDER_ID_1]")
    )


@pytest.mark.parametrize(
    "written",
    [
        _written("Deliveries take a few days [S9].", "S9"),
        _written("Deliveries take a few days [S1].", "S1", "S2"),
        _written("Deliveries take a few days [S1].", "S2"),
        _written("Deliveries take a few days and we hope it arrives soon."),
        _written("Hello!\n\n[S1]", "S1"),
    ],
)
def test_unknown_mismatched_or_missing_citations_fail_grounding(written: WrittenDraft) -> None:
    assert _rejection(written) == GROUNDING_FAILED


@pytest.mark.parametrize(
    "text",
    [
        "Hello!\n\nWe can refund you soon.\n\nYour parcel is in_transit [S2].",
        "Hello!\n\nIt takes 5 days.\n\nYour parcel is in_transit [S2].",
        "Thank you for writing to us, we will look into it right away.\n\nIt is in_transit [S2].",
    ],
)
def test_an_uncited_long_segment_or_an_uncited_commitment_fails(text: str) -> None:
    assert _rejection(_written(text, "S2")) == GROUNDING_FAILED


def test_an_order_citation_must_repeat_the_value_of_its_field() -> None:
    assert _rejection(_written("Your parcel is on its way [S2].", "S2")) == GROUNDING_FAILED
    assert check_draft(_written("Your parcel is IN_TRANSIT [S2].", "S2"), FULL_REQUEST, MAX_CHARS)


@pytest.mark.parametrize(
    "text",
    [
        "Your refund is approved, so you are eligible for a new order [S3].",
        "Your refund is approved under our policy [S3].",
        "Refunds arrive within 5 days, and yours is approved [S3].",
    ],
)
def test_a_policy_supported_only_by_an_order_citation_fails(text: str) -> None:
    assert _rejection(_written(text, "S3")) == GROUNDING_FAILED


def test_a_policy_with_a_kb_citation_and_a_fact_with_an_order_citation_pass() -> None:
    written = _written("Your refund is approved [S3]. Refunds follow our policy [S1].", "S3", "S1")

    assert check_draft(written, FULL_REQUEST, MAX_CHARS).citations[0] == OrderContextCitation(
        "S3", OrderFieldName("refund_status")
    )


def test_a_clarification_may_go_without_citations_but_never_with_a_commitment() -> None:
    asking = _written(
        "Could you tell us which item you mean, so we can look at it?", clarification=True
    )
    promising = _written("Could you tell us the item? We will refund it.", clarification=True)

    assert check_draft(asking, FULL_REQUEST, MAX_CHARS).citations == ()
    assert _rejection(promising) == GROUNDING_FAILED


def _with_fact(value: str) -> DraftRequest:
    return dataclasses.replace(
        REQUEST, order_facts=(OrderFact(source_id="S2", field="refund_amount", value=value),)
    )


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("10", "Your refund amount is 100 [S2]."),
        ("shipped", "Your parcel is unshipped [S2]."),
        ("1", "Your order [ORDER_ID_1] is refunded [S2]."),
        ("12.5", "Your refund amount is 12.50 [S2]."),
    ],
)
def test_an_order_value_must_appear_whole(value: str, text: str) -> None:
    assert _rejection(_written(text, "S2"), _with_fact(value)) == GROUNDING_FAILED


def test_an_order_value_may_be_followed_by_punctuation() -> None:
    draft = check_draft(
        _written("Your parcel is in_transit [S2].", "S2"), _with_fact("in_transit"), MAX_CHARS
    )

    assert draft.segments[0].text == "Your parcel is in_transit."


def test_a_removed_citation_takes_the_spaces_before_it() -> None:
    draft = check_draft(
        _written("Deliveries take a few days  [S1], and more [S1] .", "S1"), FULL_REQUEST, MAX_CHARS
    )

    assert draft.segments[0].text == "Deliveries take a few days, and more ."


def test_a_draft_longer_than_the_contract_allows_is_invalid_output() -> None:
    half = MAX_DRAFT_CHARS // 2 - 1
    fitting = _written(f"{'a' * half} [S1]\n\n{'b' * half} [S1]", "S1")
    too_long = _written(f"{'a' * half} [S1]\n\n{'b' * (half + 1)} [S1]", "S1")

    assert check_draft(fitting, FULL_REQUEST, MAX_CHARS)
    assert _rejection(too_long) == LLM_INVALID_OUTPUT


def test_a_short_draft_without_any_citation_fails_unless_it_asks_for_information() -> None:
    assert _rejection(_written("Hello!")) == GROUNDING_FAILED
    assert check_draft(_written("Hello!", clarification=True), FULL_REQUEST, MAX_CHARS)


def test_an_uncited_segment_may_be_exactly_as_long_as_the_limit() -> None:
    fitting = _written(f"{'x' * MAX_CHARS}\n\nIt is in_transit [S2].", "S2")
    too_long = _written(f"{'x' * (MAX_CHARS + 1)}\n\nIt is in_transit [S2].", "S2")

    assert check_draft(fitting, FULL_REQUEST, MAX_CHARS)
    assert _rejection(too_long) == GROUNDING_FAILED
