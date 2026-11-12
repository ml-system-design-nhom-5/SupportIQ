"""Guardrail: the ticket workflow keeps personal and AI text out of telemetry and ai-service.

A replica runs with its claim loop, the logging setup and redactor of the process, and the
redacting span processor (TEST-26, LOG-29). A customer writes a message with every value that
backend holds for the ticket; its suggestion job pseudonymizes it and calls an in-memory
ai-service that serves the contract's examples; staff then use every console operation built
so far. No seeded value reaches a request to ai-service (FR-09, SEC-36), and no seeded value,
message text, or AI text reaches a log line or a span.

The test waits for the events of the jobs, never for real time: the waits of the clock end
only on a wake-up of the claim loop, and the bound fails the test instead of letting it hang
(TEST-14).
"""

import asyncio
import io
from dataclasses import dataclass
from uuid import UUID

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from supportiq_backend.accounts import PasswordHash
from supportiq_backend.composition_root import BackgroundWork, create_app
from supportiq_backend.composition_root.cli import build_redactor
from supportiq_backend.platform import MILLISECONDS_PER_SECOND, EventName
from supportiq_backend.platform.adapters.logging_setup import (
    StandardLibraryEventRecorder,
    configure_logging,
)
from tests.integration.accounts.password_requests import sign_in
from tests.integration.ai_service_doubles import (
    EXAMPLE_OF_PATH,
    FakeAiService,
    serve_examples,
)
from tests.integration.application import ORIGIN_HEADERS, build_settings, running_app
from tests.integration.builders import (
    AccountSpec,
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    RefundSpec,
    ShipmentSpec,
)
from tests.integration.claim_loop_doubles import SignallingEventRecorder, WakeUpOnlyClock
from tests.integration.database import WorkerDatabase
from tests.integration.guardrails.exported_spans import spans_as_text
from tests.unit.accounts.fakes import KNOWN_PASSWORD

pytestmark = pytest.mark.anyio

DISPLAY_NAME = "Vu Quynh Telemetria"
NAME_PARTS = ("Quynh", "Telemetria")
CUSTOMER_LOGIN = "customer-workflow"
STAFF_LOGIN = "staff-workflow"
STAFF_DISPLAY_NAME = "Staff Workflowmember"
UNKNOWN_TRACKING_CODE = "TRK-0000077777"
PRIVATE_WORDS = "it holds a private gift"
AI_TEXTS = ("thank you for your patience", "Check each statement against its cited source")
SESSION_COOKIE = "supportiq_session"
# The longest that the whole flow may take before the test fails.
BOUND_MS = 10_000
TICKET_KEY = "00000000-0000-4000-8000-0000000000b1"
VIEW_KEY = "00000000-0000-4000-8000-0000000000a1"
CORRECTION_KEY = "00000000-0000-4000-8000-0000000000a2"
REPLY_KEY = "00000000-0000-4000-8000-0000000000a3"


@dataclass(frozen=True, slots=True)
class Scenario:
    """The seeded ticket values and the message that carries all of them.

    Attributes:
        order_id: The customer's order.
        seeded_values: Every personal value of the ticket that backend holds.
        message: The customer's message, with every seeded value in it.
    """

    order_id: str
    seeded_values: tuple[str, ...]
    message: str


async def column(builder: DatabaseBuilder, statement: str, **parameters: object) -> str:
    return str(await builder.scalar(statement, **parameters))


@pytest.fixture
async def scenario(builder: DatabaseBuilder, known_password_hash: PasswordHash) -> Scenario:
    customer_id = await insert_accounts(builder, known_password_hash)
    # A shipment gives a tracking code, and a refund the field that the example draft cites.
    order_id = await builder.order(
        customer_id,
        OrderSpec(
            lines=(LineSpec(await builder.product()),),
            shipment=ShipmentSpec(),
            refund=RefundSpec(),
        ),
    )
    of_customer = "FROM customers WHERE customer_id = :id"
    of_order = "FROM orders WHERE order_id = :id"
    email = await column(builder, f"SELECT email {of_customer}", id=customer_id)
    phone = await column(builder, f"SELECT phone {of_customer}", id=customer_id)
    address = await column(builder, f"SELECT shipping_address {of_order}", id=order_id)
    transaction_id = await column(builder, f"SELECT transaction_id {of_order}", id=order_id)
    tracking_code = await column(
        builder, "SELECT tracking_code FROM shipments WHERE order_id = :id", id=order_id
    )
    message = (
        f"Hi, I am {DISPLAY_NAME}, {NAME_PARTS[0]} for short. Order {order_id} was paid with "
        f"{transaction_id} and sent as {tracking_code}, not {UNKNOWN_TRACKING_CODE}, to "
        f"{address}. Mail {email} or call {phone}; {PRIVATE_WORDS}."
    )
    seeded = (DISPLAY_NAME, *NAME_PARTS, email, phone, order_id, address, transaction_id)
    return Scenario(order_id, (*seeded, tracking_code, UNKNOWN_TRACKING_CODE), message)


async def insert_accounts(builder: DatabaseBuilder, password_hash: PasswordHash) -> UUID:
    customer_id = await builder.customer(display_name=DISPLAY_NAME)
    await builder.account(
        AccountSpec(
            "customer",
            customer_id=customer_id,
            login_name=CUSTOMER_LOGIN,
            password_hash=password_hash,
        )
    )
    await builder.account(
        AccountSpec(
            "staff",
            login_name=STAFF_LOGIN,
            display_name=STAFF_DISPLAY_NAME,
            password_hash=password_hash,
        )
    )
    return customer_id


def headers_of(response: httpx.Response, key: str | None = None) -> dict[str, str]:
    cookie = {"Cookie": f"{SESSION_COOKIE}={response.cookies[SESSION_COOKIE]}"}
    return {**ORIGIN_HEADERS, **cookie, **({} if key is None else {"Idempotency-Key": key})}


async def use_the_console(
    client: httpx.AsyncClient,
    staff: httpx.Response,
    ticket_id: str,
    events: SignallingEventRecorder,
) -> int:
    read = headers_of(staff)
    path = f"/v1/console/tickets/{ticket_id}"
    await client.get("/v1/console/tickets", params={"status": "open"}, headers=read)
    await client.get(path, headers=read)
    await client.post(f"{path}/views", headers=headers_of(staff, VIEW_KEY))
    created = await client.post(
        f"{path}/suggestions",
        json={"intent_override": "refund_status"},
        headers=headers_of(staff, CORRECTION_KEY),
    )
    corrected = created.json()["suggestion_id"]
    await events.wait_for(EventName.SUGGESTION_COMPLETED, suggestion_id=corrected)
    await client.get(path, headers=read)
    sent = await client.post(
        f"{path}/replies",
        json={
            "basis": "ai_draft",
            "suggestion_id": corrected,
            "body": "Hello, your refund request is under review.",
            "acknowledged_warning_ids": [],
        },
        headers=headers_of(staff, REPLY_KEY),
    )
    return sent.status_code


@pytest.mark.usefixtures("restored_root_logger")
async def test_no_personal_or_ai_text_reaches_telemetry_or_ai_service(
    worker_database: WorkerDatabase, scenario: Scenario, exported_spans: InMemorySpanExporter
) -> None:
    log_stream = io.StringIO()
    events = SignallingEventRecorder(
        StandardLibraryEventRecorder(configure_logging(log_stream, build_redactor()))
    )
    ai_service = FakeAiService(serve_examples)
    app = create_app(
        build_settings(worker_database),
        events,
        WakeUpOnlyClock(),
        background=BackgroundWork.SUGGESTION_JOBS,
        ai_service_transport=ai_service,
    )

    async with asyncio.timeout(BOUND_MS / MILLISECONDS_PER_SECOND), running_app(app) as client:
        customer = await sign_in(client, CUSTOMER_LOGIN, KNOWN_PASSWORD)
        created = await client.post(
            "/v1/shop/tickets",
            json={"order_id": scenario.order_id, "message": scenario.message},
            headers=headers_of(customer, TICKET_KEY),
        )
        await events.wait_for(EventName.SUGGESTION_COMPLETED)
        staff = await sign_in(client, STAFF_LOGIN, KNOWN_PASSWORD)
        reply_status = await use_the_console(client, staff, created.json()["ticket_id"], events)

    logs = log_stream.getvalue()
    spans = spans_as_text(exported_spans)
    forbidden = (*scenario.seeded_values, scenario.message, PRIVATE_WORDS, *AI_TEXTS)
    assert reply_status == httpx.codes.CREATED
    sent_to_ai_service = ai_service.sent_text()
    assert set(ai_service.paths()) == set(EXAMPLE_OF_PATH)
    assert [value for value in scenario.seeded_values if value in sent_to_ai_service] == []
    assert [value for value in forbidden if value in logs] == []
    assert [value for value in forbidden if value in spans] == []
    assert '"event":"suggestion.completed"' in logs
    assert '"event":"reply.sent"' in logs
    assert "'run_suggestion_job'" in spans
