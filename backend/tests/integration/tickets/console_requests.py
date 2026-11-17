"""What the tests of the console's ticket operations share: staff, tickets, and suggestions.

The application runs without the claim loop and without ai-service (`BackgroundWork.NONE`),
so a suggestion with results is inserted as the owner, in the form that the claim loop
stores: each part result is the body that ai-service answered, and the request holds the
order context that was sent. Every value is synthetic (TEST-18).
"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import httpx
from sqlalchemy import update

from supportiq_backend.suggestions.adapters.tables import SuggestionPartRow
from tests.integration.application import session_headers
from tests.integration.builders import (
    AccountSpec,
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    SuggestionPartSpec,
    SuggestionSpec,
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
OTHER_KEY = "00000000-0000-4000-8000-000000000002"
MANAGER_NAME = "Manager One"
PROPOSALS = "/reply-proposals"
ESCALATIONS = "/escalations"
REPLIES = "/replies"
FORBIDDEN = "urn:supportiq:problem:forbidden"
INVALID_TICKET_STATE = "urn:supportiq:problem:invalid-ticket-state"
SUGGESTION_PENDING = "urn:supportiq:problem:suggestion-pending"
SUGGESTION_SUPERSEDED = "urn:supportiq:problem:suggestion-superseded"
AUTHORITY_REQUIRED = "urn:supportiq:problem:authority-required"
# A suggestion and a proposal that no ticket has.
UNKNOWN_SUGGESTION_ID = "00000000-0000-4000-8000-0000000000f2"
UNKNOWN_PROPOSAL_ID = "00000000-0000-4000-8000-0000000000f3"
TICKET_STATUS = "SELECT status FROM tickets WHERE ticket_id = :ticket_id"
# The decision rows of the tests, without their IDs and times, as one JSON value per row.
DECISION_ROWS = """
    SELECT jsonb_agg(jsonb_build_object(
        'decision_type', decision_type, 'suggestion_id', suggestion_id,
        'staff_reason_codes', staff_reason_codes, 'change_ratio', change_ratio,
        'final_intent', final_intent, 'decided_by', decided_by_account_id,
        'proposed_by', proposed_by_account_id, 'is_proposal_changed', is_proposal_changed
    ))
    FROM staff_decisions
"""


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


async def sign_in_as_manager(builder: DatabaseBuilder) -> SupportSession:
    """Sign in a new manager whose display name differs from that of staff."""
    account_id = await builder.account(AccountSpec("manager", display_name=MANAGER_NAME))
    return SupportSession(account_id, session_headers(await builder.session(account_id, "manager")))


async def act_on_ticket(
    client: httpx.AsyncClient,
    session: SupportSession,
    path: str,
    body: object,
    key: str = KEY,
) -> httpx.Response:
    """Send a state-changing console request with a key, such as a proposal on a ticket path."""
    return await client.post(path, json=body, headers=key_headers(session.headers, key))


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


async def insert_suggestion(builder: DatabaseBuilder, ticket_id: str, spec: SuggestionSpec) -> str:
    """Insert a suggestion as the ticket's current one and return its ID as text."""
    return str(await builder.suggestion(ticket_id, spec))


async def complete_draft(worker_database: WorkerDatabase, suggestion_id: str) -> None:
    """Store `draft_ready_outcome` in a pending draft part, as the claim loop stores a result.

    Args:
        worker_database: The database of the worker.
        suggestion_id: The suggestion whose draft part is pending.
    """
    engine = create_owner_engine(worker_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                update(SuggestionPartRow)
                .where(
                    SuggestionPartRow.suggestion_id == UUID(suggestion_id),
                    SuggestionPartRow.part == "draft",
                )
                .values(
                    status="draft_ready",
                    completed_at=PART_COMPLETED_AT,
                    result=draft_ready_outcome(),
                )
            )
    finally:
        await engine.dispose()


async def ticket_status(builder: DatabaseBuilder, ticket_id: str) -> object:
    return await builder.scalar(TICKET_STATUS, ticket_id=ticket_id)


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


def stored_suggestion(
    *,
    analysis: SuggestionPartSpec | None = None,
    draft: SuggestionPartSpec | None = None,
    request: dict[str, object] | None = None,
) -> SuggestionSpec:
    """A suggestion created at `SUGGESTION_CREATED_AT`; a part left out is `pending`."""
    return SuggestionSpec(
        created_at=SUGGESTION_CREATED_AT, request=request, analysis=analysis, draft=draft
    )


def analysis_ready_draft_pending() -> SuggestionSpec:
    return stored_suggestion(
        analysis=stored_part("ready", ready_analysis()), request=sent_request()
    )


def draft_ready() -> SuggestionSpec:
    return stored_suggestion(
        analysis=stored_part("ready", ready_analysis()),
        draft=stored_part("draft_ready", draft_ready_outcome()),
        request=sent_request(),
    )


def stored_part(status: str, result: dict[str, object] | None = None) -> SuggestionPartSpec:
    """A stored part; a part that is not `pending` completed at `PART_COMPLETED_AT`."""
    completed_at = None if status == PENDING else PART_COMPLETED_AT
    return SuggestionPartSpec(status, completed_at, result=result)


def without_fields(response: httpx.Response, *names: str) -> dict[str, object]:
    return {name: value for name, value in response.json().items() if name not in names}


async def count_replies(builder: DatabaseBuilder) -> object:
    return await builder.scalar("SELECT count(*) FROM replies")
