"""Tests of the order facts and of the facts that a draft cites, which must have been sent."""

from collections.abc import Mapping
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
    OrderFact,
    read_cited_facts,
    read_order_fact,
)
from tests.unit.suggestions.builders import (
    DOCUMENT_ID,
    DOCUMENT_VERSION,
    build_draft_ready,
    build_no_draft,
)

# Every field has its own value, so reading the wrong field fails the test.
PLACED_AT = datetime(2026, 11, 1, 8, 12, 30, tzinfo=UTC)
ESTIMATED_DELIVERY_AT = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)
DELIVERED_AT = datetime(2026, 11, 6, 10, 45, tzinfo=UTC)
REFUND_REQUESTED_AT = datetime(2026, 11, 7, 9, 5, tzinfo=UTC)
ORDER_TOTAL = Money(4_250, "USD")
SHIPPING_COST = Money(500, "USD")
REFUND_AMOUNT = Money(3_750, "USD")
FULL_CONTEXT = OrderContext(
    order_status=OrderStatus.SHIPPED,
    placed_at=PLACED_AT,
    order_total=ORDER_TOTAL,
    shipping_cost=SHIPPING_COST,
    shipment_status=ShipmentStatus.DELAYED,
    estimated_delivery_at=ESTIMATED_DELIVERY_AT,
    delivered_at=DELIVERED_AT,
    refund_status=RefundStatus.REQUESTED,
    refund_amount=REFUND_AMOUNT,
    refund_requested_at=REFUND_REQUESTED_AT,
)
FACTS_OF_FULL_CONTEXT: Mapping[OrderContextField, OrderFact] = {
    OrderContextField.ORDER_STATUS: OrderStatus.SHIPPED,
    OrderContextField.PLACED_AT: PLACED_AT,
    OrderContextField.ORDER_TOTAL: ORDER_TOTAL,
    OrderContextField.SHIPPING_COST: SHIPPING_COST,
    OrderContextField.SHIPMENT_STATUS: ShipmentStatus.DELAYED,
    OrderContextField.ESTIMATED_DELIVERY_AT: ESTIMATED_DELIVERY_AT,
    OrderContextField.DELIVERED_AT: DELIVERED_AT,
    OrderContextField.REFUND_STATUS: RefundStatus.REQUESTED,
    OrderContextField.REFUND_AMOUNT: REFUND_AMOUNT,
    OrderContextField.REFUND_REQUESTED_AT: REFUND_REQUESTED_AT,
}
CONTEXT_WITHOUT_REFUND = replace(
    FULL_CONTEXT, refund_status=None, refund_amount=None, refund_requested_at=None
)
KB_CITATION = KbDocumentCitation("c1", DOCUMENT_ID, DOCUMENT_VERSION, "Sample text.")


def citing(*fields: OrderContextField) -> DraftReady:
    ready = build_draft_ready()
    citations = tuple(
        OrderContextCitation(f"o{index}", field) for index, field in enumerate(fields, start=1)
    )
    return replace(ready, draft=Draft(ready.draft.segments, (KB_CITATION, *citations)))


@pytest.mark.parametrize("field", list(OrderContextField))
def test_every_field_of_a_full_context_has_its_own_fact(field: OrderContextField) -> None:
    assert read_order_fact(FULL_CONTEXT, field) == FACTS_OF_FULL_CONTEXT[field]


def test_a_field_without_a_value_has_no_fact() -> None:
    assert read_order_fact(CONTEXT_WITHOUT_REFUND, OrderContextField.REFUND_STATUS) is None


def test_a_draft_that_cites_sent_facts_returns_them_in_citation_order() -> None:
    outcome = citing(OrderContextField.REFUND_AMOUNT, OrderContextField.ORDER_STATUS)

    facts = read_cited_facts(outcome, FULL_CONTEXT)

    assert facts == (REFUND_AMOUNT, OrderStatus.SHIPPED)


def test_a_draft_that_cites_a_field_without_a_value_is_outside_the_contract() -> None:
    with pytest.raises(AiServiceContractError):
        read_cited_facts(citing(OrderContextField.REFUND_STATUS), CONTEXT_WITHOUT_REFUND)


def test_an_order_citation_without_an_order_context_is_outside_the_contract() -> None:
    with pytest.raises(AiServiceContractError):
        read_cited_facts(citing(OrderContextField.ORDER_STATUS), None)


def test_a_draft_that_cites_only_documents_has_no_cited_facts() -> None:
    assert read_cited_facts(citing(), None) == ()


def test_an_outcome_without_a_draft_cites_no_facts() -> None:
    assert read_cited_facts(build_no_draft(NoDraftStatus.ABSTAINED), None) == ()
