"""The console's mappings that need no database: order facts, pending views, unique items.

The order mappings are the real functions of commerce, which the composition root passes in.
"""

import json
from datetime import UTC, datetime

import pytest

from supportiq_backend.commerce import Money, OrderStatus, RefundStatus, ShipmentStatus
from supportiq_backend.commerce.api.shop import to_money, to_order_view
from supportiq_backend.platform import RequestContractError, UnexpectedFailureError
from supportiq_backend.platform.web import render_json
from supportiq_backend.suggestions import OrderContext, OrderContextCitation, OrderContextField
from supportiq_backend.tickets.api.console_citation_views import to_citation_view
from supportiq_backend.tickets.api.console_request_fields import parse_unique_items
from supportiq_backend.tickets.api.console_suggestion_views import to_pending_suggestion_view
from supportiq_backend.tickets.api.order_views import OrderViewMappers
from tests.unit.suggestions.builders import build_analysis, build_suggestion

ORDER_VIEWS = OrderViewMappers(to_order_view=to_order_view, to_money=to_money)
CITATION_ID = "c1"
LOCATION = "body.staff_reason_codes"
SENT_CONTEXT = OrderContext(
    order_status=OrderStatus.DELIVERED,
    placed_at=datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
    order_total=Money(4_250, "USD"),
    shipping_cost=Money(300, "USD"),
    shipment_status=ShipmentStatus.DELIVERED,
    estimated_delivery_at=datetime(2026, 11, 3, 17, 0, tzinfo=UTC),
    delivered_at=datetime(2026, 11, 3, 15, 30, 0, 250_000, tzinfo=UTC),
    refund_status=RefundStatus.UNDER_REVIEW,
    refund_amount=Money(1_000, "USD"),
    refund_requested_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (OrderContextField.ORDER_STATUS, "delivered"),
        (OrderContextField.PLACED_AT, "2026-11-01T08:00:00Z"),
        (OrderContextField.ORDER_TOTAL, {"amount_minor": 4_250, "currency": "USD"}),
        (OrderContextField.SHIPPING_COST, {"amount_minor": 300, "currency": "USD"}),
        (OrderContextField.SHIPMENT_STATUS, "delivered"),
        (OrderContextField.ESTIMATED_DELIVERY_AT, "2026-11-03T17:00:00Z"),
        (OrderContextField.DELIVERED_AT, "2026-11-03T15:30:00.250000Z"),
        (OrderContextField.REFUND_STATUS, "under_review"),
        (OrderContextField.REFUND_AMOUNT, {"amount_minor": 1_000, "currency": "USD"}),
        (OrderContextField.REFUND_REQUESTED_AT, "2026-11-04T10:00:00Z"),
    ],
)
def test_order_citation_carries_the_value_of_its_field_as_it_was_sent(
    field: OrderContextField, value: object
) -> None:
    citation = OrderContextCitation(CITATION_ID, field)

    view = to_citation_view(citation, SENT_CONTEXT, ORDER_VIEWS)

    assert json.loads(render_json(view)) == {
        "source_type": "order_context",
        "citation_id": CITATION_ID,
        "field": field.value,
        "value": value,
    }


@pytest.mark.parametrize(
    "sent_context", [OrderContext(), None], ids=["field-not-sent", "no-order-context"]
)
def test_order_citation_of_a_value_that_was_not_sent_is_a_defect(
    sent_context: OrderContext | None,
) -> None:
    citation = OrderContextCitation(CITATION_ID, OrderContextField.REFUND_STATUS)

    with pytest.raises(UnexpectedFailureError):
        to_citation_view(citation, sent_context, ORDER_VIEWS)


def test_pending_view_of_a_new_suggestion_has_both_parts_pending() -> None:
    view = to_pending_suggestion_view(build_suggestion())

    rendered = json.loads(render_json(view))
    assert rendered["analysis"] == {"analysis_status": "pending"}
    assert rendered["draft"] == {"draft_status": "pending"}


def test_pending_view_of_a_suggestion_with_a_result_is_a_defect() -> None:
    suggestion = build_suggestion(analysis=build_analysis())

    with pytest.raises(UnexpectedFailureError):
        to_pending_suggestion_view(suggestion)


def test_unique_items_keep_the_order_of_the_request() -> None:
    items = parse_unique_items(("tone_or_clarity", "kb_gap"), LOCATION)

    assert items == ("tone_or_clarity", "kb_gap")


def test_repeated_item_is_refused_at_the_location_of_its_array() -> None:
    with pytest.raises(RequestContractError) as raised:
        parse_unique_items(("kb_gap", "other", "kb_gap"), LOCATION)

    assert raised.value.locations == (LOCATION,)
