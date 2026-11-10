"""Creating a shop ticket over HTTP against PostgreSQL: what it stores and what it refuses."""

from http import HTTPStatus

import pytest

from supportiq_backend.platform import EventName
from tests.integration.application import (
    ORIGIN_HEADERS,
    RunningBackend,
    build_settings,
    running_client,
    session_headers,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.tickets.shop_requests import (
    KEY,
    MESSAGE,
    MESSAGE_LIMIT,
    OTHER_KEY,
    TICKETS,
    count_tickets,
    create_ticket,
    without_trace_id,
)
from tests.unit.platform.fakes import (
    FakeClock,
    RecordingEventRecorder,
)

pytestmark = pytest.mark.anyio


async def test_creation_returns_the_view_of_the_contract(
    backend: RunningBackend, headers: dict[str, str], order_id: str
) -> None:
    response = await create_ticket(backend.client, headers, order_id)

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        "ticket_id": "TCK-1001",
        "order_id": order_id,
        "message": MESSAGE,
        "created_at": "2026-11-05T09:00:00Z",
        "customer_status": "received",
    }


async def test_ticket_starts_open_from_the_shop_with_the_default_handling_mode(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    await create_ticket(backend.client, headers, order_id)

    stored = await builder.scalar(
        "SELECT status || '/' || handling_mode || '/' || source || '/' || is_authority_required "
        "FROM tickets"
    )

    assert stored == "open/assisted/shop/false"


async def test_handling_mode_comes_from_the_setting(
    worker_database: WorkerDatabase,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    order_id: str,
) -> None:
    settings = build_settings(worker_database, default_handling_mode="manual")

    async with running_client(settings, RecordingEventRecorder(), FakeClock()) as client:
        await create_ticket(client, headers, order_id)

    assert await builder.scalar("SELECT handling_mode FROM tickets") == "manual"


async def test_message_is_stored_and_returned_exactly_as_written(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    message = "  Đơn hàng\tof mine \U0001f600\n"

    response = await create_ticket(backend.client, headers, order_id, message=message)

    assert response.json()["message"] == message
    assert await builder.scalar("SELECT body FROM customer_messages") == message


async def test_creation_records_the_event_with_the_ticket_id(
    backend: RunningBackend, headers: dict[str, str], order_id: str
) -> None:
    await create_ticket(backend.client, headers, order_id)

    (created,) = backend.events.of(EventName.TICKET_CREATED)
    assert created.attributes == {"ticket_id": "TCK-1001"}


async def test_order_of_another_customer_and_an_unknown_order_return_the_same_404(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    other_customer = await builder.customer(display_name="Other Customer")
    other_order = await builder.order_of_one_product(other_customer)

    other = await create_ticket(backend.client, headers, other_order, key=KEY)
    unknown = await create_ticket(backend.client, headers, "ORD-99999", key=OTHER_KEY)

    assert other.status_code == unknown.status_code == HTTPStatus.NOT_FOUND
    assert without_trace_id(other) == without_trace_id(unknown)
    assert other_order not in other.text
    assert await count_tickets(builder) == 0
    assert await builder.scalar("SELECT count(*) FROM idempotency_records") == 0


async def test_order_id_with_a_nul_character_is_an_unknown_order(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    response = await create_ticket(backend.client, headers, "ORD\x0020901")

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    "message",
    ["x", "x" * MESSAGE_LIMIT, "\U0001f600" * MESSAGE_LIMIT],
    ids=["one", "limit", "limit-outside-the-basic-plane"],
)
async def test_message_length_is_counted_in_code_points_up_to_the_limit(
    backend: RunningBackend, headers: dict[str, str], order_id: str, message: str
) -> None:
    response = await create_ticket(backend.client, headers, order_id, message=message)

    assert response.status_code == HTTPStatus.CREATED


@pytest.mark.parametrize(
    "message",
    ["", "x" * (MESSAGE_LIMIT + 1), "\U0001f600" * (MESSAGE_LIMIT + 1), "a\x00b"],
    ids=["empty", "over-the-limit", "over-the-limit-outside-the-basic-plane", "nul"],
)
async def test_invalid_message_returns_422_at_its_location_and_creates_nothing(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    order_id: str,
    message: str,
) -> None:
    response = await create_ticket(backend.client, headers, order_id, message=message)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["type"] == "urn:supportiq:problem:invalid-request"
    assert "body.message" in response.json()["detail"]
    assert await count_tickets(builder) == 0


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"order_id": "ORD-20901"}',
        b'{"message": "Hi"}',
        b'{"order_id": "", "message": "Hi"}',
        b'{"order_id": 20901, "message": "Hi"}',
        b'{"order_id": "ORD-20901", "message": 7}',
        b'{"order_id": "ORD-20901", "message": "Hi", "extra": true}',
        b'{"order_id": "ORD-20901", "message": "\\ud800"}',
    ],
)
async def test_body_outside_the_contract_returns_422(
    backend: RunningBackend, headers: dict[str, str], body: bytes
) -> None:
    response = await backend.client.post(
        TICKETS, content=body, headers={**headers, "Idempotency-Key": KEY}
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


@pytest.mark.parametrize("key_headers", [{}, {"Idempotency-Key": "not-a-uuid"}])
async def test_missing_or_malformed_key_returns_422(
    backend: RunningBackend,
    headers: dict[str, str],
    order_id: str,
    key_headers: dict[str, str],
) -> None:
    response = await backend.client.post(
        TICKETS,
        json={"order_id": order_id, "message": MESSAGE},
        headers={**headers, **key_headers},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_creation_without_an_origin_returns_403_before_the_session_is_read(
    backend: RunningBackend,
) -> None:
    response = await backend.client.post(TICKETS, content=b"{}")

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_creation_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.post(TICKETS, content=b"{}", headers=ORIGIN_HEADERS)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize("role", ["staff", "manager", "admin"])
async def test_another_role_gets_403_on_every_ticket_operation_whatever_it_sent(
    backend: RunningBackend, builder: DatabaseBuilder, role: str
) -> None:
    account_id = await builder.account(AccountSpec(role))
    headers = session_headers(await builder.session(account_id, role))

    created = await backend.client.post(TICKETS, content=b"not json", headers=headers)
    listed = await backend.client.get(TICKETS, params={"limit": "x"}, headers=headers)
    read = await backend.client.get(f"{TICKETS}/TCK-1001", headers=headers)

    assert created.status_code == HTTPStatus.FORBIDDEN
    assert listed.status_code == HTTPStatus.FORBIDDEN
    assert read.status_code == HTTPStatus.FORBIDDEN
