"""Reading the ticket workspace over HTTP against PostgreSQL (`getConsoleTicket`).

The orders and the amount of an order citation are mapped by the order mappings of commerce
that the composition root passes in (ARCH-17, ARCH-21).
"""

from http import HTTPStatus

import pytest

from tests.integration.application import ORIGIN_HEADERS, RunningBackend
from tests.integration.builders import (
    SUGGESTION_TRACE_ID,
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    RefundSpec,
    ShipmentSpec,
)
from tests.integration.tickets.console_requests import (
    CURRENCY,
    CUSTOMER_NAME,
    DRAFT_TEXT,
    MESSAGE,
    ORDER_PLACED_TEXT,
    OTHER_ORDER_PLACED_AT,
    OTHER_ORDER_PLACED_TEXT,
    PRODUCT_NAME,
    SHIPPING_COST_MINOR,
    SUGGESTION_CREATED_TEXT,
    TICKET_CREATED_TEXT,
    UNKNOWN_TICKET_ID,
    asset_versions,
    draft_latencies,
    draft_ready,
    draft_segments,
    insert_suggestion,
    kb_citation,
    open_ticket,
    order_total,
    ready_analysis,
    sign_in_as_support,
    stored_suggestion,
    ticket_path,
    without_fields,
)

pytestmark = pytest.mark.anyio

OTHER_ORDER_QUANTITY = 2


async def test_workspace_holds_the_ticket_in_the_shape_of_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert without_fields(response, "order") == {
        "ticket_id": ticket.ticket_id,
        "status": "open",
        "handling_mode": "assisted",
        "is_authority_required": False,
        "created_at": TICKET_CREATED_TEXT,
        "customer": {"display_name": CUSTOMER_NAME},
        "message": {"body": MESSAGE, "created_at": TICKET_CREATED_TEXT},
        "allowed_actions": ["escalate", "send_reply", "submit_reply_proposal"],
    }


async def test_workspace_holds_the_order_of_the_ticket_with_its_shipping_address(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    address = await builder.scalar(
        "SELECT shipping_address FROM orders WHERE order_id = :order_id",
        order_id=ticket.order_id,
    )

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=headers)

    assert response.json()["order"] == {
        "order_id": ticket.order_id,
        "order_status": "shipped",
        "placed_at": ORDER_PLACED_TEXT,
        "order_total": order_total(),
        "shipping_cost": {"amount_minor": SHIPPING_COST_MINOR, "currency": CURRENCY},
        "lines": [{"product_id": ticket.product_id, "product_name": PRODUCT_NAME, "quantity": 1}],
        "shipment": {"shipment_status": "not_shipped"},
        "shipping_address": address,
    }


async def test_workspace_lists_the_other_orders_of_the_customer_without_addresses(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    other_order_id = await builder.order(
        ticket.customer_id,
        OrderSpec(
            lines=(LineSpec(ticket.product_id, OTHER_ORDER_QUANTITY),),
            placed_at=OTHER_ORDER_PLACED_AT,
            shipment=ShipmentSpec(),
            refund=RefundSpec(),
        ),
    )

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=headers)

    assert response.json()["other_orders"] == [
        {
            "order_id": other_order_id,
            "order_status": "shipped",
            "shipment_status": "in_transit",
            "refund_status": "requested",
            "placed_at": OTHER_ORDER_PLACED_TEXT,
            "order_total": order_total(),
            "lines": [
                {
                    "product_id": ticket.product_id,
                    "product_name": PRODUCT_NAME,
                    "quantity": OTHER_ORDER_QUANTITY,
                }
            ],
        }
    ]


async def test_workspace_shows_the_ready_draft_with_the_value_of_each_order_citation(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    suggestion_id = await insert_suggestion(builder, ticket.ticket_id, draft_ready())

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=headers)

    assert response.json()["suggestion"] == {
        "suggestion_id": suggestion_id,
        "trigger": "ticket_created",
        "created_at": SUGGESTION_CREATED_TEXT,
        "trace_id": SUGGESTION_TRACE_ID,
        "analysis": {"analysis_status": "ready", **ready_analysis()},
        "draft": {
            "draft_status": "draft_ready",
            "segments": draft_segments(),
            "citations": [
                {
                    "source_type": "order_context",
                    "citation_id": "c1",
                    "field": "order_total",
                    "value": order_total(),
                },
                kb_citation(),
            ],
            "text": DRAFT_TEXT,
            "reason_codes": [],
            "versions": asset_versions(),
            "step_latencies": draft_latencies(),
        },
    }


async def test_ready_draft_allows_staff_to_correct_the_intent(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, draft_ready())

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=headers)

    assert response.json()["allowed_actions"] == [
        "correct_intent",
        "escalate",
        "send_reply",
        "submit_reply_proposal",
    ]


async def test_pending_suggestion_shows_both_parts_pending_and_blocks_sending(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, stored_suggestion())

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=headers)

    workspace = response.json()
    assert workspace["suggestion"]["analysis"] == {"analysis_status": "pending"}
    assert workspace["suggestion"]["draft"] == {"draft_status": "pending"}
    assert workspace["allowed_actions"] == ["escalate"]


async def test_unknown_ticket_returns_404(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers

    response = await backend.client.get(ticket_path(UNKNOWN_TICKET_ID), headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_workspace_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.get(ticket_path(UNKNOWN_TICKET_ID), headers=ORIGIN_HEADERS)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
