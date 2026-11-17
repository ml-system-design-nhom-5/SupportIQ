"""Reading the caller's tickets over HTTP against PostgreSQL (SEC-17, CON-14).

A ticket shows `replied` with the reply once staff sent it through `sendReply`, and never any
AI output (contract `ShopTicketView`).
"""

from datetime import timedelta
from http import HTTPStatus
from uuid import UUID

import pytest

from supportiq_backend.platform.web import encode_cursor
from tests.integration.application import (
    RunningBackend,
)
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.tickets.shop_requests import (
    NEWEST,
    OLDEST,
    REPLY_BODY,
    REPLY_SENT_AT,
    TICKETS,
    create_ticket,
    send_reply,
    sign_in_as_new_customer,
    without_trace_id,
)
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
)

pytestmark = pytest.mark.anyio


async def test_customer_reads_a_ticket_created_through_the_shop(
    backend: RunningBackend, headers: dict[str, str], order_id: str
) -> None:
    created = await create_ticket(backend.client, headers, order_id)

    response = await backend.client.get(f"{TICKETS}/TCK-1001", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == created.json()


async def test_customer_reads_the_reply_that_staff_sent(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    ticket_id = await builder.ticket(customer_id, order_id)
    await send_reply(backend.client, builder, ticket_id)

    response = await backend.client.get(f"{TICKETS}/{ticket_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["customer_status"] == "replied"
    assert response.json()["reply"] == {"body": REPLY_BODY, "sent_at": REPLY_SENT_AT}


async def test_ticket_without_a_reply_is_received_and_has_no_reply(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    ticket_id = await builder.ticket(customer_id, order_id)

    response = await backend.client.get(f"{TICKETS}/{ticket_id}", headers=headers)

    assert response.json()["customer_status"] == "received"
    assert "reply" not in response.json()


async def test_list_shows_the_reply_only_on_the_ticket_that_has_one(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    replied = await builder.ticket(customer_id, order_id, TicketSpec(created_at=NEWEST))
    received = await builder.ticket(customer_id, order_id, TicketSpec(created_at=OLDEST))
    await send_reply(backend.client, builder, replied)

    response = await backend.client.get(TICKETS, headers=headers)

    newest, oldest = response.json()["items"]
    assert (newest["ticket_id"], newest["customer_status"]) == (replied, "replied")
    assert newest["reply"] == {"body": REPLY_BODY, "sent_at": REPLY_SENT_AT}
    assert (oldest["ticket_id"], oldest["customer_status"]) == (received, "received")
    assert "reply" not in oldest


async def test_unknown_imported_and_foreign_tickets_return_the_same_404(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
) -> None:
    other_customer = await builder.customer(display_name="Other Customer")
    other_order = await builder.order_of_one_product(other_customer)
    foreign = await builder.ticket(other_customer, other_order)
    imported = await builder.ticket(customer_id, None, TicketSpec(source="import"))

    responses = [
        await backend.client.get(f"{TICKETS}/{ticket_id}", headers=headers)
        for ticket_id in (foreign, imported, "TCK-999999")
    ]

    assert {response.status_code for response in responses} == {HTTPStatus.NOT_FOUND}
    assert without_trace_id(responses[0]) == without_trace_id(responses[1])
    assert without_trace_id(responses[1]) == without_trace_id(responses[2])


async def test_ticket_id_with_a_nul_character_is_an_unknown_ticket(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    response = await backend.client.get(f"{TICKETS}/TCK%00", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_customer_without_tickets_gets_an_empty_page(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    response = await backend.client.get(TICKETS, headers=headers)

    assert response.json() == {"items": []}


async def test_list_is_newest_first_and_follows_the_cursor(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    oldest = await builder.ticket(customer_id, order_id, TicketSpec(created_at=OLDEST))
    newest = await builder.ticket(customer_id, order_id, TicketSpec(created_at=NEWEST))
    middle = await builder.ticket(customer_id, order_id, TicketSpec(created_at=FAKE_CLOCK_START))

    first = await backend.client.get(TICKETS, params={"limit": "2"}, headers=headers)
    second = await backend.client.get(
        TICKETS, params={"cursor": first.json()["next_cursor"]}, headers=headers
    )

    assert [item["ticket_id"] for item in first.json()["items"]] == [newest, middle]
    assert [item["ticket_id"] for item in second.json()["items"]] == [oldest]
    assert "next_cursor" not in second.json()


async def test_tickets_of_one_time_are_ordered_by_ticket_id_by_code_point(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    await builder.scalar("SELECT setval('ticket_number_seq', 9998)")
    spec = TicketSpec(created_at=FAKE_CLOCK_START)
    four_digits = await builder.ticket(customer_id, order_id, spec)
    five_digits = await builder.ticket(customer_id, order_id, spec)

    first = await backend.client.get(TICKETS, params={"limit": "1"}, headers=headers)
    second = await backend.client.get(
        TICKETS, params={"cursor": first.json()["next_cursor"]}, headers=headers
    )

    assert [item["ticket_id"] for item in first.json()["items"]] == [five_digits]
    assert [item["ticket_id"] for item in second.json()["items"]] == [four_digits]


async def test_cursor_keeps_the_microseconds_of_the_last_ticket(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    earlier = await builder.ticket(customer_id, order_id, TicketSpec(created_at=FAKE_CLOCK_START))
    later = await builder.ticket(
        customer_id,
        order_id,
        TicketSpec(created_at=FAKE_CLOCK_START + timedelta(microseconds=1)),
    )

    first = await backend.client.get(TICKETS, params={"limit": "1"}, headers=headers)
    second = await backend.client.get(
        TICKETS, params={"cursor": first.json()["next_cursor"]}, headers=headers
    )

    assert [item["ticket_id"] for item in first.json()["items"]] == [later]
    assert [item["ticket_id"] for item in second.json()["items"]] == [earlier]


async def test_cursor_holds_the_time_and_the_ticket_id_and_no_order_id(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    spec = TicketSpec(created_at=FAKE_CLOCK_START)
    first_ticket = await builder.ticket(customer_id, order_id, spec)
    await builder.ticket(customer_id, order_id, spec)

    response = await backend.client.get(
        TICKETS, params={"limit": "1", "order_id": order_id}, headers=headers
    )

    assert response.json()["next_cursor"] == encode_cursor(
        "listShopTickets",
        {"created_at": "2026-11-05T09:00:00Z", "ticket_id": first_ticket},
    )


async def test_order_filter_holds_on_every_page_without_being_in_the_cursor(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    other_order = await builder.order_of_one_product(customer_id)
    newest = await builder.ticket(customer_id, order_id, TicketSpec(created_at=NEWEST))
    await builder.ticket(customer_id, other_order, TicketSpec(created_at=FAKE_CLOCK_START))
    oldest = await builder.ticket(customer_id, order_id, TicketSpec(created_at=OLDEST))
    params = {"limit": "1", "order_id": order_id}

    first = await backend.client.get(TICKETS, params=params, headers=headers)
    second = await backend.client.get(
        TICKETS,
        params={"order_id": order_id, "cursor": first.json()["next_cursor"]},
        headers=headers,
    )

    assert [item["ticket_id"] for item in first.json()["items"]] == [newest]
    assert [item["ticket_id"] for item in second.json()["items"]] == [oldest]
    assert "next_cursor" not in second.json()


async def test_list_never_holds_imported_or_foreign_tickets_on_any_page(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    other_customer = await builder.customer(display_name="Other Customer")
    other_order = await builder.order_of_one_product(other_customer)
    own = await builder.ticket(customer_id, order_id, TicketSpec(created_at=NEWEST))
    await builder.ticket(other_customer, other_order, TicketSpec(created_at=FAKE_CLOCK_START))
    await builder.ticket(customer_id, order_id, TicketSpec(source="import", created_at=OLDEST))
    await builder.ticket(customer_id, None, TicketSpec(source="import", created_at=OLDEST))

    response = await backend.client.get(TICKETS, headers=headers)

    assert [item["ticket_id"] for item in response.json()["items"]] == [own]


async def test_cursor_of_another_customer_shows_only_the_tickets_of_the_caller(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
    order_id: str,
) -> None:
    other_id, other_headers = await sign_in_as_new_customer(builder)
    other_order = await builder.order_of_one_product(other_id)
    spec = TicketSpec(created_at=FAKE_CLOCK_START)
    await builder.ticket(other_id, other_order, spec)
    await builder.ticket(other_id, other_order, spec)
    own = await builder.ticket(customer_id, order_id, TicketSpec(created_at=OLDEST))
    foreign_page = await backend.client.get(TICKETS, params={"limit": "1"}, headers=other_headers)

    response = await backend.client.get(
        TICKETS, params={"cursor": foreign_page.json()["next_cursor"]}, headers=headers
    )

    assert [item["ticket_id"] for item in response.json()["items"]] == [own]


async def test_order_filter_with_a_foreign_or_unknown_order_returns_the_same_404(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    other_customer = await builder.customer(display_name="Other Customer")
    other_order = await builder.order_of_one_product(other_customer)

    other = await backend.client.get(TICKETS, params={"order_id": other_order}, headers=headers)
    unknown = await backend.client.get(TICKETS, params={"order_id": "ORD-99999"}, headers=headers)
    nul = await backend.client.get(TICKETS, params={"order_id": "ORD\x00"}, headers=headers)

    assert other.status_code == unknown.status_code == nul.status_code == HTTPStatus.NOT_FOUND
    assert without_trace_id(other) == without_trace_id(unknown)


async def test_empty_order_filter_returns_422(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    response = await backend.client.get(TICKETS, params={"order_id": ""}, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["type"] == "urn:supportiq:problem:invalid-request"
    assert "order_id" in response.json()["detail"]


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "garbage!",
        encode_cursor("listShopOrders", {"position": 1}),
        encode_cursor("listShopTickets", {"created_at": "yesterday", "ticket_id": "TCK-1"}),
        encode_cursor("listShopTickets", {"created_at": "2026-11-05T09:00:00", "ticket_id": "T"}),
        encode_cursor("listShopTickets", {"created_at": 7, "ticket_id": "TCK-1"}),
        encode_cursor(
            "listShopTickets", {"created_at": "2026-11-05T09:00:00Z", "ticket_id": "a\x00b"}
        ),
    ],
)
async def test_malformed_or_foreign_cursor_returns_422(
    backend: RunningBackend, headers: dict[str, str], cursor: str
) -> None:
    response = await backend.client.get(TICKETS, params={"cursor": cursor}, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


@pytest.mark.parametrize("limit", ["0", "101", "x"])
async def test_limit_outside_the_range_returns_422(
    backend: RunningBackend, headers: dict[str, str], limit: str
) -> None:
    response = await backend.client.get(TICKETS, params={"limit": limit}, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_ticket_of_an_account_with_no_session_returns_401(backend: RunningBackend) -> None:
    listed = await backend.client.get(TICKETS)
    read = await backend.client.get(f"{TICKETS}/TCK-1001")

    assert listed.status_code == read.status_code == HTTPStatus.UNAUTHORIZED
