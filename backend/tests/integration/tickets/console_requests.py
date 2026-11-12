"""What the tests of the console's ticket operations share: staff, tickets, and suggestions.

The application runs without the claim loop and without ai-service (`BackgroundWork.NONE`),
so a suggestion with results is inserted as the owner, in the form that the claim loop
stores: each part result is the body that ai-service answered, and the request holds the
order context that was sent. Every value is synthetic (TEST-18).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

import httpx
from sqlalchemy import insert, null, update
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.suggestions.adapters.tables import SuggestionPartRow, SuggestionRow
from supportiq_backend.tickets.adapters.tables import TicketRow
from tests.integration.application import session_headers
from tests.integration.builders import (
    AccountSpec,
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    TicketSpec,
)
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.unit.platform.fakes import FAKE_CLOCK_START

CONSOLE_TICKETS = "/v1/console/tickets"
KEY = "00000000-0000-4000-8000-000000000001"
# An absent key, one that is not a UUID, and one that is not lowercase (contract `IdempotencyKey`).
INVALID_KEY_HEADERS: tuple[dict[str, str], ...] = (
    {},
    {"Idempotency-Key": "not-a-uuid"},
    {"Idempotency-Key": "00000000-0000-4000-8000-00000000000A"},
)
INVALID_KEY_IDS = ("missing", "malformed", "uppercase")
UNKNOWN_TICKET_ID = "TCK-999999"
INVALID_REQUEST = "urn:supportiq:problem:invalid-request"
CUSTOMER_NAME = "Lan Tran"
STAFF_NAME = "Staff One"
MESSAGE = "Where is my parcel?"
PRODUCT_NAME = "Desk lamp"
# The amounts of every order of `DatabaseBuilder.order`, in USD cents.
ORDER_TOTAL_MINOR = 4_250
SHIPPING_COST_MINOR = 0
CURRENCY = "USD"
TICKET_CREATED_AT = FAKE_CLOCK_START - timedelta(hours=1)
ORDER_PLACED_AT = FAKE_CLOCK_START - timedelta(days=2)
OTHER_ORDER_PLACED_AT = FAKE_CLOCK_START - timedelta(days=9)
SUGGESTION_CREATED_AT = FAKE_CLOCK_START - timedelta(minutes=30)
PART_COMPLETED_AT = FAKE_CLOCK_START - timedelta(minutes=29)
# The same times as the contract writes them.
NOW_TEXT = "2026-11-05T09:00:00Z"
TICKET_CREATED_TEXT = "2026-11-05T08:00:00Z"
ORDER_PLACED_TEXT = "2026-11-03T09:00:00Z"
OTHER_ORDER_PLACED_TEXT = "2026-10-27T09:00:00Z"
SUGGESTION_CREATED_TEXT = "2026-11-05T08:30:00Z"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
WARNING_ID = "w1"
PREDICTED_INTENT = "track_order"
PREDICTED_PROBABILITY = 0.91
CORRECTED_INTENT = "delivery_time"
# The canonical text of the draft of `draft_ready_outcome`: segments of one paragraph joined
# by a space, paragraphs by a blank line (contracts v1 design).
DRAFT_TEXT = (
    "Thank you for your patience. Your order total was charged once.\n\n"
    "This sample sentence stands for a policy statement from the cited document."
)
PENDING = "pending"


@dataclass(frozen=True, slots=True)
class PartSpec:
    """One stored part of a suggestion.

    Attributes:
        status: The stored status, such as `pending`, `ready`, or `draft_ready`.
        result: The body that ai-service answered; absent for a part without a result.
    """

    status: str = PENDING
    result: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SuggestionSpec:
    """A suggestion to insert as a ticket's current one.

    Attributes:
        analysis: The analysis part.
        draft: The draft part.
        request: The stored request, with the order context that was sent; absent before
            pseudonymization.
    """

    analysis: PartSpec = field(default_factory=PartSpec)
    draft: PartSpec = field(default_factory=PartSpec)
    request: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SupportSession:
    """A signed-in member of support.

    Attributes:
        account_id: The account.
        headers: The headers of its requests: the session cookie and an allowed `Origin`.
    """

    account_id: UUID
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class ConsoleTicket:
    """A ticket of a new customer with one order, as the builders inserted it.

    Attributes:
        ticket_id: The ticket.
        customer_id: Its customer.
        order_id: Its order.
        product_id: The product of the order's only line.
    """

    ticket_id: str
    customer_id: UUID
    order_id: str
    product_id: str


def ticket_path(ticket_id: str, operation: str = "") -> str:
    return f"{CONSOLE_TICKETS}/{ticket_id}{operation}"


def key_headers(headers: dict[str, str], key: str = KEY) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


async def sign_in_as_support(builder: DatabaseBuilder, role: str = "staff") -> SupportSession:
    account_id = await builder.account(AccountSpec(role, display_name=STAFF_NAME))
    return SupportSession(account_id, session_headers(await builder.session(account_id, role)))


async def open_ticket(builder: DatabaseBuilder, spec: TicketSpec | None = None) -> ConsoleTicket:
    customer_id = await builder.customer(display_name=CUSTOMER_NAME)
    product_id = await builder.product(name=PRODUCT_NAME)
    order_id = await builder.order(
        customer_id, OrderSpec(lines=(LineSpec(product_id),), placed_at=ORDER_PLACED_AT)
    )
    ticket_id = await builder.ticket(
        customer_id, order_id, spec or TicketSpec(message=MESSAGE, created_at=TICKET_CREATED_AT)
    )
    return ConsoleTicket(ticket_id, customer_id, order_id, product_id)


async def insert_suggestion(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, ticket_id: str, spec: SuggestionSpec
) -> str:
    """Insert a suggestion with its two parts and make it the ticket's current one.

    Args:
        worker_database: The database of the worker.
        builder: Gives the suggestion a deterministic ID.
        ticket_id: The ticket.
        spec: The parts and the request.

    Returns:
        The suggestion ID.
    """
    suggestion_id = builder.next_uuid()
    engine = create_owner_engine(worker_database)
    try:
        await _insert_suggestion_rows(engine, suggestion_id, ticket_id, spec)
    finally:
        await engine.dispose()
    return str(suggestion_id)


def asset_versions() -> dict[str, object]:
    return {
        "release_id": "release-test-1",
        "model_version": "intent-model-test-1",
        "kb_version": "kb-test-1",
        "mapping_version": "mapping-test-1",
        "prompt_version": "prompts-test-1",
        "routing_version": "routing-test-1",
        "index_version": "index-test-1",
    }


def ready_analysis() -> dict[str, object]:
    """Return an `Analysis` of the ai-service contract with one warning and one document."""
    return {
        "intent": {
            "source": "model",
            "label": PREDICTED_INTENT,
            "probability": PREDICTED_PROBABILITY,
            "confidence_band": "high",
        },
        "alternatives": [{"label": "track_delivery", "probability": 0.05}],
        "is_in_scope": True,
        "documents": [
            {
                "document_id": "SAMPLE-SHIPPING-001",
                "version": "1.0",
                "title": "Sample shipping document",
                "policy_key": "sample_shipping_times",
                "effective_start_at": "2026-01-01T00:00:00Z",
                "effective_end_at": "2027-01-01T00:00:00Z",
                "validity": "valid",
                "rank": 1,
                "snippet": "This is sample text. It is not KB content and not a policy.",
            }
        ],
        "routing": {"recommendation": "draft", "reason_codes": []},
        "warnings": [{"warning_id": WARNING_ID, "reason_code": "source_review_overdue"}],
        "versions": asset_versions(),
        "step_latencies": {"total_ms": 176, "analysis_ms": 176},
    }


def draft_ready_outcome() -> dict[str, object]:
    """Return a `DraftOutcome` of the ai-service contract that cites the order total."""
    return {
        "status": "draft_ready",
        "reason_codes": [],
        "analysis": ready_analysis(),
        "draft": {
            "segments": draft_segments(),
            "citations": [
                {"source_type": "order_context", "citation_id": "c1", "field": "order_total"},
                kb_citation(),
            ],
        },
        "versions": asset_versions(),
        "step_latencies": draft_latencies(),
        "mask_count_by_type": {"email": 0, "phone": 0, "card": 0},
    }


def draft_segments() -> list[dict[str, object]]:
    """Return the segments of the draft, whose canonical text is `DRAFT_TEXT`."""
    return [
        {
            "segment_id": "s1",
            "paragraph_index": 0,
            "text": "Thank you for your patience.",
            "citation_ids": [],
        },
        {
            "segment_id": "s2",
            "paragraph_index": 0,
            "text": "Your order total was charged once.",
            "citation_ids": ["c1"],
        },
        {
            "segment_id": "s3",
            "paragraph_index": 1,
            "text": "This sample sentence stands for a policy statement from the cited document.",
            "citation_ids": ["c2"],
        },
    ]


def kb_citation() -> dict[str, object]:
    return {
        "source_type": "kb_document",
        "citation_id": "c2",
        "document_id": "SAMPLE-SHIPPING-001",
        "version": "1.0",
        "snippet": "This is sample text. It is not KB content and not a policy.",
    }


def draft_latencies() -> dict[str, object]:
    return {"total_ms": 3_420, "analysis_ms": 176, "llm_ms": 3_205}


def order_total() -> dict[str, object]:
    return {"amount_minor": ORDER_TOTAL_MINOR, "currency": CURRENCY}


def sent_request() -> dict[str, object]:
    """Return the `SuggestionRequest` that was sent, with the order total of the order."""
    return {
        "message": MESSAGE,
        "order_context": {"order_total": order_total()},
        "as_of": TICKET_CREATED_TEXT,
    }


def analysis_ready_draft_pending() -> SuggestionSpec:
    return SuggestionSpec(analysis=PartSpec("ready", ready_analysis()), request=sent_request())


def draft_ready() -> SuggestionSpec:
    return SuggestionSpec(
        analysis=PartSpec("ready", ready_analysis()),
        draft=PartSpec("draft_ready", draft_ready_outcome()),
        request=sent_request(),
    )


def without_fields(response: httpx.Response, *names: str) -> dict[str, object]:
    return {name: value for name, value in response.json().items() if name not in names}


async def count_replies(builder: DatabaseBuilder) -> object:
    return await builder.scalar("SELECT count(*) FROM replies")


async def _insert_suggestion_rows(
    engine: AsyncEngine, suggestion_id: UUID, ticket_id: str, spec: SuggestionSpec
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(SuggestionRow).values(
                suggestion_id=suggestion_id,
                ticket_id=ticket_id,
                trigger="ticket_created",
                created_at=SUGGESTION_CREATED_AT,
                trace_id=TRACE_ID,
                request=null() if spec.request is None else spec.request,
            )
        )
        for part, part_spec in (("analysis", spec.analysis), ("draft", spec.draft)):
            await connection.execute(
                insert(SuggestionPartRow).values(
                    suggestion_id=suggestion_id,
                    part=part,
                    status=part_spec.status,
                    reason_codes=[],
                    completed_at=None if part_spec.status == PENDING else PART_COMPLETED_AT,
                    result=null() if part_spec.result is None else part_spec.result,
                )
            )
        await connection.execute(
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id)
            .values(current_suggestion_id=suggestion_id)
        )
