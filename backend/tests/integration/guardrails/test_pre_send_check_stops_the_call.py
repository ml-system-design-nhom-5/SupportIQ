"""Guardrail: a text with personal data left in it never reaches ai-service (TEST-26, FR-09).

A replica runs with its claim loop and every detector that backend runs. The message holds the
customer's phone with letters stuck to it, so no detector finds it, and the pre-send check
finds its digits as a known value inside a run of digits (ADR-0029, statement 4). The job sends
nothing, ends both parts unavailable with `pseudonymization_failed`, and keeps no map row. The
test waits for the event of the job, and the bound fails it instead of letting it hang
(TEST-14).
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.composition_root import BackgroundWork, create_app
from app.platform import MILLISECONDS_PER_SECOND, EventName
from app.suggestions import SuggestionTicketId
from tests.integration.ai_service_doubles import FakeAiService, serve_examples
from tests.integration.application import build_settings, running_app
from tests.integration.builders import DatabaseBuilder, LineSpec, OrderSpec, TicketSpec
from tests.integration.claim_loop_doubles import SignallingEventRecorder, WakeUpOnlyClock
from tests.integration.database import WorkerDatabase
from tests.integration.workflow.workflow_rows import start_suggestion, ticket_created
from tests.unit.platform.fakes import RecordingEventRecorder

pytestmark = pytest.mark.anyio

BOUND_MS = 10_000
CUSTOMER_PHONE = "SELECT phone FROM customers WHERE customer_id = :customer_id"
PARTS_STOPPED = (
    "SELECT count(*) FROM suggestion_parts WHERE suggestion_id = :suggestion_id"
    " AND status = 'unavailable' AND reason_codes = '[\"pseudonymization_failed\"]'::jsonb"
)
COUNT_MAP_ROWS = "SELECT count(*) FROM pseudonym_map_entries WHERE ticket_id = :ticket_id"
FAILURE_REASON = (
    "SELECT data ->> 'failure_reason' FROM audit_log_entries"
    " WHERE ticket_id = :ticket_id AND event_type = 'message.pseudonymized'"
)
BOTH_PARTS = 2


async def insert_ticket_with_the_phone_left(builder: DatabaseBuilder) -> SuggestionTicketId:
    """Insert a customer, an order, and a ticket whose message holds the phone, stuck to "pm"."""
    _account_id, customer_id = await builder.customer_account()
    phone = await builder.scalar(CUSTOMER_PHONE, customer_id=customer_id)
    product_id = await builder.product()
    order_id = await builder.order(customer_id, OrderSpec(lines=(LineSpec(product_id),)))
    message = f"Please call me back at {phone}pm today."
    return SuggestionTicketId(
        await builder.ticket(customer_id, order_id, TicketSpec(message=message))
    )


async def test_personal_data_left_stops_the_call_to_ai_service(
    worker_database: WorkerDatabase, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket_with_the_phone_left(builder)
    suggestion_id = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    events = SignallingEventRecorder(RecordingEventRecorder())
    ai_service = FakeAiService(serve_examples)
    app = create_app(
        build_settings(worker_database),
        events,
        WakeUpOnlyClock(events),
        background=BackgroundWork.SUGGESTION_JOBS,
        ai_service_transport=ai_service,
    )

    async with asyncio.timeout(BOUND_MS / MILLISECONDS_PER_SECOND), running_app(app):
        await events.wait_for(EventName.TICKET_MANUAL_HANDLING_STARTED)

    assert ai_service.requests == []
    assert await builder.scalar(PARTS_STOPPED, suggestion_id=suggestion_id) == BOTH_PARTS
    assert await builder.scalar(COUNT_MAP_ROWS, ticket_id=ticket_id) == 0
    assert await builder.scalar(FAILURE_REASON, ticket_id=ticket_id) == "personal_data_left"
