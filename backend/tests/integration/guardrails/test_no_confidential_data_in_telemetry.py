"""Guardrail: Confidential data and secrets never reach logs or traces (TEST-26, LOG-29).

The whole pipeline of a replica runs here: the logging setup and the redactor of the process,
and the tracer provider with its redacting span processor. The requests carry every kind of
value that the design names: message text, display names, order IDs in URLs and elsewhere,
shipping addresses, passwords, and a raw cookie value.
"""

import io
from dataclasses import dataclass

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.accounts import PasswordHash
from app.composition_root.process_logging import build_redactor
from app.platform.adapters.logging_setup import (
    StandardLibraryEventRecorder,
    configure_logging,
)
from tests.integration.accounts.password_requests import sign_in
from tests.integration.application import ORIGIN_HEADERS, build_settings, running_client
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.guardrails.exported_spans import spans_as_text
from tests.unit.accounts.fakes import KNOWN_PASSWORD
from tests.unit.platform.fakes import FakeClock

pytestmark = pytest.mark.anyio

LOGIN_NAME = "customer-telemetry"
ADMIN_LOGIN_NAME = "admin-telemetry"
WRONG_PASSWORD = "a-wrong-test-password"
DISPLAY_NAME = "Nguyen Thi Telemetry"
STAFF_DISPLAY_NAME = "Tran Van Telemetry"
MESSAGE_TEXT = "Please call me about the parcel, it holds a private gift"
UNKNOWN_ORDER = "ORD-99999"
KEY = "00000000-0000-4000-8000-000000000001"
OTHER_KEY = "00000000-0000-4000-8000-000000000002"
SESSION_COOKIE = "supportiq_session"


@dataclass(frozen=True, slots=True)
class Scenario:
    """The records and the secrets that the requests of the test use.

    Attributes:
        order_id: An order of the customer.
        shipping_address: Its shipping address.
        transaction_id: Its transaction ID.
        staff_account_id: A staff account that the admin changes.
    """

    order_id: str
    shipping_address: str
    transaction_id: str
    staff_account_id: str


@pytest.fixture
async def scenario(builder: DatabaseBuilder, known_password_hash: PasswordHash) -> Scenario:
    customer_id = await builder.customer(display_name=DISPLAY_NAME)
    await builder.account(
        AccountSpec(
            "customer",
            customer_id=customer_id,
            display_name=DISPLAY_NAME,
            login_name=LOGIN_NAME,
            password_hash=known_password_hash,
        )
    )
    await builder.account(
        AccountSpec("admin", login_name=ADMIN_LOGIN_NAME, password_hash=known_password_hash)
    )
    order_id = await builder.order_of_one_product(customer_id)
    return Scenario(
        order_id=order_id,
        shipping_address=str(
            await builder.scalar(
                "SELECT shipping_address FROM orders WHERE order_id = :order_id",
                order_id=order_id,
            )
        ),
        transaction_id=str(
            await builder.scalar(
                "SELECT transaction_id FROM orders WHERE order_id = :order_id",
                order_id=order_id,
            )
        ),
        staff_account_id=str(
            await builder.account(AccountSpec("staff", display_name=STAFF_DISPLAY_NAME))
        ),
    )


async def send_every_kind_of_customer_request(
    client: httpx.AsyncClient, headers: dict[str, str], order_id: str
) -> None:
    await client.get("/v1/sessions/current", headers=headers)
    await client.get("/v1/shop/orders", headers=headers)
    await client.get(f"/v1/shop/orders/{order_id}", headers=headers)
    await client.get(f"/v1/shop/orders/{UNKNOWN_ORDER}", headers=headers)
    await client.get("/v1/shop/tickets", params={"order_id": order_id}, headers=headers)
    await client.get("/v1/shop/tickets", params={"order_id": UNKNOWN_ORDER}, headers=headers)
    created = await client.post(
        "/v1/shop/tickets",
        json={"order_id": order_id, "message": MESSAGE_TEXT},
        headers={**headers, "Idempotency-Key": KEY},
    )
    await client.post(
        "/v1/shop/tickets",
        json={"order_id": UNKNOWN_ORDER, "message": MESSAGE_TEXT},
        headers={**headers, "Idempotency-Key": OTHER_KEY},
    )
    await client.post(
        "/v1/shop/tickets",
        json={"order_id": order_id, "message": f"{MESSAGE_TEXT}\x00"},
        headers={**headers, "Idempotency-Key": OTHER_KEY},
    )
    await client.get(f"/v1/shop/tickets/{created.json()['ticket_id']}", headers=headers)


async def send_every_kind_of_admin_request(
    client: httpx.AsyncClient, headers: dict[str, str], staff_account_id: str
) -> None:
    await client.get("/v1/admin/accounts", headers=headers)
    await client.get("/v1/shop/orders", headers=headers)
    await client.post(
        f"/v1/admin/accounts/{staff_account_id}/role-changes",
        json={"role": "manager"},
        headers={**headers, "Idempotency-Key": KEY},
    )


def forbidden_values(scenario: Scenario, cookies: tuple[str, ...]) -> tuple[str, ...]:
    return (
        KNOWN_PASSWORD,
        WRONG_PASSWORD,
        *cookies,
        DISPLAY_NAME,
        STAFF_DISPLAY_NAME,
        LOGIN_NAME,
        ADMIN_LOGIN_NAME,
        MESSAGE_TEXT,
        scenario.order_id,
        UNKNOWN_ORDER,
        scenario.shipping_address,
        scenario.transaction_id,
    )


async def send_every_kind_of_request(
    client: httpx.AsyncClient, scenario: Scenario
) -> tuple[str, ...]:
    await sign_in(client, LOGIN_NAME, WRONG_PASSWORD)
    customer = await sign_in(client, LOGIN_NAME, KNOWN_PASSWORD)
    admin = await sign_in(client, ADMIN_LOGIN_NAME, KNOWN_PASSWORD)
    customer_cookie = customer.cookies[SESSION_COOKIE]
    admin_cookie = admin.cookies[SESSION_COOKIE]
    await send_every_kind_of_customer_request(
        client,
        {**ORIGIN_HEADERS, "Cookie": f"{SESSION_COOKIE}={customer_cookie}"},
        scenario.order_id,
    )
    await send_every_kind_of_admin_request(
        client,
        {**ORIGIN_HEADERS, "Cookie": f"{SESSION_COOKIE}={admin_cookie}"},
        scenario.staff_account_id,
    )
    return customer_cookie, admin_cookie


@pytest.mark.usefixtures("restored_root_logger")
async def test_no_confidential_value_or_secret_reaches_a_log_or_a_span(
    worker_database: WorkerDatabase, scenario: Scenario, exported_spans: InMemorySpanExporter
) -> None:
    log_stream = io.StringIO()
    events = StandardLibraryEventRecorder(configure_logging(log_stream, build_redactor()))

    async with running_client(build_settings(worker_database), events, FakeClock()) as client:
        cookies = await send_every_kind_of_request(client, scenario)

    logs = log_stream.getvalue()
    spans = spans_as_text(exported_spans)
    forbidden = forbidden_values(scenario, cookies)
    assert [value for value in forbidden if value in logs] == []
    assert [value for value in forbidden if value in spans] == []
    assert '"event":"ticket.created"' in logs
    assert '"http_route":"/v1/shop/orders/{order_id}"' in logs
    assert "/v1/shop/orders/{order_id}" in spans
    assert "'create_ticket'" in spans
    assert "'ticket_id': 'TCK-1001'" in spans
