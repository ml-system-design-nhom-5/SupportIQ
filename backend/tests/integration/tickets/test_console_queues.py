"""Listing the console queues over HTTP against PostgreSQL (`listConsoleTickets`, CON-14)."""

from datetime import timedelta
from http import HTTPStatus

import pytest

from supportiq_backend.platform import OperationId
from supportiq_backend.platform.web import encode_cursor
from supportiq_backend.tickets import MESSAGE_EXCERPT_LENGTH
from tests.integration.application import ORIGIN_HEADERS, RunningBackend
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.tickets.console_requests import (
    CONSOLE_TICKETS,
    CUSTOMER_NAME,
    INVALID_REQUEST,
    MESSAGE,
    PREDICTED_INTENT,
    PREDICTED_PROBABILITY,
    TICKET_CREATED_AT,
    TICKET_CREATED_TEXT,
    analysis_ready_draft_pending,
    insert_suggestion,
    open_ticket,
    sign_in_as_support,
)

pytestmark = pytest.mark.anyio

STATUS_DETAIL = "The parameter status must be open, awaiting_approval, escalated, or closed."
CURSOR_DETAIL = "The parameter cursor is not a cursor of this operation."
OPEN_QUEUE = {"status": "open"}


async def test_open_queue_lists_a_ticket_in_the_shape_of_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    response = await backend.client.get(CONSOLE_TICKETS, params=OPEN_QUEUE, headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "items": [
            {
                "ticket_id": ticket.ticket_id,
                "created_at": TICKET_CREATED_TEXT,
                "status": "open",
                "handling_mode": "assisted",
                "is_authority_required": False,
                "customer": {"display_name": CUSTOMER_NAME},
                "message_excerpt": MESSAGE,
            }
        ]
    }


async def test_summary_shows_the_draft_status_and_the_predicted_intent(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, analysis_ready_draft_pending())

    response = await backend.client.get(CONSOLE_TICKETS, params=OPEN_QUEUE, headers=headers)

    (item,) = response.json()["items"]
    assert item["draft_status"] == "pending"
    assert item["predicted_intent"] == {
        "label": PREDICTED_INTENT,
        "probability": PREDICTED_PROBABILITY,
        "confidence_band": "high",
    }


async def test_message_excerpt_holds_the_first_160_characters(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    message = "x" * MESSAGE_EXCERPT_LENGTH + "y"
    await open_ticket(builder, TicketSpec(message=message))

    response = await backend.client.get(CONSOLE_TICKETS, params=OPEN_QUEUE, headers=headers)

    (item,) = response.json()["items"]
    assert item["message_excerpt"] == "x" * MESSAGE_EXCERPT_LENGTH


async def test_open_queue_is_oldest_first_and_follows_the_cursor_to_the_last_page(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    newer = await open_ticket(builder, TicketSpec(created_at=TICKET_CREATED_AT))
    older = await open_ticket(
        builder, TicketSpec(created_at=TICKET_CREATED_AT - timedelta(minutes=1))
    )

    first = await backend.client.get(
        CONSOLE_TICKETS, params={**OPEN_QUEUE, "limit": "1"}, headers=headers
    )
    second = await backend.client.get(
        CONSOLE_TICKETS,
        params={**OPEN_QUEUE, "cursor": first.json()["next_cursor"]},
        headers=headers,
    )

    assert [item["ticket_id"] for item in first.json()["items"]] == [older.ticket_id]
    assert [item["ticket_id"] for item in second.json()["items"]] == [newer.ticket_id]
    assert "next_cursor" not in second.json()


@pytest.mark.parametrize(
    "params", [{}, {"status": "pending"}, {"status": "OPEN"}], ids=["missing", "unknown", "case"]
)
async def test_missing_or_unknown_status_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, params: dict[str, str]
) -> None:
    headers = (await sign_in_as_support(builder)).headers

    response = await backend.client.get(CONSOLE_TICKETS, params=params, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["type"] == INVALID_REQUEST
    assert response.json()["detail"] == STATUS_DETAIL


@pytest.mark.parametrize(
    "cursor",
    [
        "not a cursor",
        encode_cursor(OperationId.LIST_SHOP_TICKETS.value, {"ticket_id": "TCK-1001"}),
    ],
    ids=["malformed", "of-another-operation"],
)
async def test_cursor_that_is_not_of_this_operation_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, cursor: str
) -> None:
    headers = (await sign_in_as_support(builder)).headers

    response = await backend.client.get(
        CONSOLE_TICKETS, params={**OPEN_QUEUE, "cursor": cursor}, headers=headers
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == CURSOR_DETAIL


async def test_cursor_of_another_queue_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder, "manager")).headers
    await open_ticket(builder, TicketSpec(created_at=TICKET_CREATED_AT))
    await open_ticket(builder, TicketSpec(created_at=TICKET_CREATED_AT + timedelta(minutes=1)))
    open_page = await backend.client.get(
        CONSOLE_TICKETS, params={**OPEN_QUEUE, "limit": "1"}, headers=headers
    )

    response = await backend.client.get(
        CONSOLE_TICKETS,
        params={"status": "closed", "cursor": open_page.json()["next_cursor"]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == CURSOR_DETAIL


async def test_staff_asking_for_another_queue_than_open_get_403(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers

    response = await backend.client.get(
        CONSOLE_TICKETS, params={"status": "closed"}, headers=headers
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_list_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.get(CONSOLE_TICKETS, params=OPEN_QUEUE, headers=ORIGIN_HEADERS)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
