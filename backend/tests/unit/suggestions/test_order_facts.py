"""Tests of the order facts and of the check that a draft cites only facts it was sent."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from supportiq_backend.commerce import Money, OrderStatus, RefundStatus, ShipmentStatus
from supportiq_backend.suggestions import (
    AiServiceContractError,
    Draft,
    DraftReady,
    KbDocumentCitation,
    NoDraftStatus,
    OrderContext,
    OrderContextCitation,
    OrderContextField,
    check_cited_facts,
    read_order_fact,
)
from tests.unit.suggestions.builders import build_draft_ready, build_no_draft

MOMENT = datetime(2026, 11, 5, 8, 12, 30, tzinfo=UTC)
AMOUNT = Money(4_250, "USD")
FULL_CONTEXT = OrderContext(
    order_status=OrderStatus.DELIVERED,
    placed_at=MOMENT,
    order_total=AMOUNT,
    shipping_cost=AMOUNT,
    shipment_status=ShipmentStatus.DELIVERED,
    estimated_delivery_at=MOMENT,
    delivered_at=MOMENT,
    refund_status=RefundStatus.REQUESTED,
    refund_amount=AMOUNT,
    refund_requested_at=MOMENT,
)
CONTEXT_WITHOUT_REFUND = replace(
    FULL_CONTEXT, refund_status=None, refund_amount=None, refund_requested_at=None
)
KB_CITATION = KbDocumentCitation("c1", "SAMPLE-REFUND-001", "1.0", "Sample text.")


def citing(*fields: OrderContextField) -> DraftReady:
    ready = build_draft_ready()
    citations = tuple(
        OrderContextCitation(f"o{index}", field) for index, field in enumerate(fields, start=1)
    )
    return replace(ready, draft=Draft(ready.draft.segments, (KB_CITATION, *citations)))


@pytest.mark.parametrize("field", list(OrderContextField))
def test_every_field_of_a_full_context_has_a_fact(field: OrderContextField) -> None:
    assert read_order_fact(FULL_CONTEXT, field) is not None


def test_a_field_without_a_value_has_no_fact() -> None:
    assert read_order_fact(CONTEXT_WITHOUT_REFUND, OrderContextField.REFUND_STATUS) is None


def test_a_draft_that_cites_sent_facts_is_accepted() -> None:
    outcome = citing(OrderContextField.ORDER_STATUS, OrderContextField.REFUND_STATUS)

    check_cited_facts(outcome, FULL_CONTEXT)


def test_a_draft_that_cites_a_field_without_a_value_is_outside_the_contract() -> None:
    with pytest.raises(AiServiceContractError):
        check_cited_facts(citing(OrderContextField.REFUND_STATUS), CONTEXT_WITHOUT_REFUND)


def test_an_order_citation_without_an_order_context_is_outside_the_contract() -> None:
    with pytest.raises(AiServiceContractError):
        check_cited_facts(citing(OrderContextField.ORDER_STATUS), None)


def test_a_draft_that_cites_only_documents_needs_no_order_context() -> None:
    check_cited_facts(citing(), None)


def test_an_outcome_without_a_draft_cites_nothing() -> None:
    check_cited_facts(build_no_draft(NoDraftStatus.ABSTAINED), None)
