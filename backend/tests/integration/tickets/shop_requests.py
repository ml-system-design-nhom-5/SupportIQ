"""What the tests of the shop's ticket operations share."""

from datetime import timedelta
from uuid import UUID

import httpx

from tests.integration.application import (
    session_headers,
)
from tests.integration.builders import DatabaseBuilder
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
)

TICKETS = "/v1/shop/tickets"
KEY = "00000000-0000-4000-8000-000000000001"
OTHER_KEY = "00000000-0000-4000-8000-000000000002"
MESSAGE = "Where is my parcel?"
SHORT_LOCK_MS = 50
MESSAGE_LIMIT = 2_000
HELD_REQUEST_HASH = bytes(32)
RETENTION_MS = 86_400_000
NEWEST = FAKE_CLOCK_START + timedelta(hours=2)
OLDEST = FAKE_CLOCK_START - timedelta(hours=2)
type Customer = tuple[UUID, dict[str, str]]


def without_trace_id(response: httpx.Response) -> dict[str, object]:
    return {name: value for name, value in response.json().items() if name != "trace_id"}


async def create_ticket(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    order_id: str,
    *,
    message: str = MESSAGE,
    key: str = KEY,
) -> httpx.Response:
    return await client.post(
        TICKETS,
        json={"order_id": order_id, "message": message},
        headers={**headers, "Idempotency-Key": key},
    )


async def sign_in_as_new_customer(builder: DatabaseBuilder) -> Customer:
    account_id, customer_id = await builder.customer_account()
    return customer_id, session_headers(await builder.session(account_id, "customer"))


async def count_tickets(builder: DatabaseBuilder) -> object:
    return await builder.scalar("SELECT count(*) FROM tickets")
