"""Manual handling end to end over HTTP, while ai-service refuses every connection (NFR-07).

New shop tickets take the handling mode `manual` from the settings. A ticket in manual mode
gets no suggestion, no job, and no call to ai-service; staff view it, propose, escalate, and
reply with the basis `no_ai_draft` only, and a manager sends its reply (backend ticket workflow
design, Manual handling). The in-memory ai-service of these tests keeps every request, so
each test proves that none was sent.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from http import HTTPStatus

import httpx
import pytest

from tests.integration.ai_service_doubles import FakeAiService, refuse_connection
from tests.integration.application import build_settings, running_client
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.tickets.console_requests import (
    ESCALATIONS,
    INVALID_TICKET_STATE,
    OTHER_KEY,
    PROPOSALS,
    REPLIES,
    act_on_ticket,
    key_headers,
    sign_in_as_manager,
    sign_in_as_support,
    ticket_path,
)
from tests.integration.tickets.shop_requests import create_ticket, sign_in_as_new_customer
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

PROPOSED_TEXT = "A manager will confirm the shipping options for your city."
REPLY_TEXT = "We ship to your city. Shipping is free for orders over 30 USD."
UNKNOWN_SUGGESTION_ID = "00000000-0000-4000-8000-0000000000f2"
SUGGESTION_SUPERSEDED = "urn:supportiq:problem:suggestion-superseded"
WITHOUT_DRAFT = {"basis": "no_ai_draft", "body": REPLY_TEXT}
MANUAL_ACTIONS = ["escalate", "send_reply", "submit_reply_proposal"]
TICKET_STATUS = "SELECT status FROM tickets WHERE ticket_id = :ticket_id"


@dataclass(frozen=True, slots=True)
class ManualDesk:
    """A replica whose new shop tickets are manual, and one such ticket.

    Attributes:
        client: An HTTP client whose requests go to the replica.
        ai_service: The in-memory ai-service that refuses every connection.
        ticket_id: A ticket that a customer created through the shop.
        customer_headers: The headers of that customer's session.
    """

    client: httpx.AsyncClient
    ai_service: FakeAiService
    ticket_id: str
    customer_headers: dict[str, str]


@pytest.fixture
async def desk(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> AsyncIterator[ManualDesk]:
    ai_service = FakeAiService(refuse_connection)
    settings = build_settings(worker_database, default_handling_mode="manual")
    customer_id, customer_headers = await sign_in_as_new_customer(builder)
    order_id = await builder.order_of_one_product(customer_id)
    async with running_client(
        settings, RecordingEventRecorder(), FakeClock(), ai_service=ai_service
    ) as client:
        created = await create_ticket(client, customer_headers, order_id)
        yield ManualDesk(client, ai_service, created.json()["ticket_id"], customer_headers)


async def ticket_status(builder: DatabaseBuilder, ticket_id: str) -> object:
    return await builder.scalar(TICKET_STATUS, ticket_id=ticket_id)


async def test_a_manual_shop_ticket_gets_no_suggestion_and_no_job(
    desk: ManualDesk, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)

    workspace = await desk.client.get(ticket_path(desk.ticket_id), headers=staff.headers)

    assert workspace.json()["handling_mode"] == "manual"
    assert "suggestion" not in workspace.json()
    assert workspace.json()["allowed_actions"] == MANUAL_ACTIONS
    assert await builder.scalar("SELECT count(*) FROM suggestions") == 0
    assert await builder.scalar("SELECT count(*) FROM suggestion_jobs") == 0
    assert desk.ai_service.requests == []


async def test_the_first_view_of_a_manual_ticket_calls_no_ai_service(
    desk: ManualDesk, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)

    response = await desk.client.post(
        ticket_path(desk.ticket_id, "/views"), headers=key_headers(staff.headers)
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert (
        await builder.scalar(
            "SELECT handling_started_at IS NOT NULL FROM tickets WHERE ticket_id = :ticket_id",
            ticket_id=desk.ticket_id,
        )
        is True
    )
    assert desk.ai_service.requests == []


async def test_a_manual_ticket_refuses_a_suggestion_with_409(
    desk: ManualDesk, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)

    response = await act_on_ticket(
        desk.client, staff, ticket_path(desk.ticket_id, "/suggestions"), {}
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.CONFLICT,
        INVALID_TICKET_STATE,
    )
    assert await builder.scalar("SELECT count(*) FROM suggestions") == 0
    assert desk.ai_service.requests == []


async def test_staff_reply_to_a_manual_ticket_without_a_draft(
    desk: ManualDesk, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)

    response = await act_on_ticket(
        desk.client, staff, ticket_path(desk.ticket_id, REPLIES), WITHOUT_DRAFT
    )

    assert (response.status_code, response.json()["basis"]) == (HTTPStatus.CREATED, "no_ai_draft")
    assert await ticket_status(builder, desk.ticket_id) == "closed"
    assert await builder.scalar("SELECT count(*) FROM staff_decisions") == 0
    assert desk.ai_service.requests == []


async def test_a_manual_ticket_is_proposed_and_a_manager_sends_the_proposal(
    desk: ManualDesk, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    proposed = await act_on_ticket(
        desk.client,
        staff,
        ticket_path(desk.ticket_id, PROPOSALS),
        {"basis": "no_ai_draft", "body": PROPOSED_TEXT},
    )

    sent = await act_on_ticket(
        desk.client,
        manager,
        ticket_path(desk.ticket_id, REPLIES),
        {
            "basis": "reply_proposal",
            "body": PROPOSED_TEXT,
            "proposal_id": proposed.json()["proposal_id"],
        },
        OTHER_KEY,
    )

    assert proposed.status_code == HTTPStatus.CREATED
    assert (sent.status_code, sent.json()["proposal_id"]) == (
        HTTPStatus.CREATED,
        proposed.json()["proposal_id"],
    )
    assert "suggestion_id" not in sent.json()
    assert await ticket_status(builder, desk.ticket_id) == "closed"
    assert await builder.scalar("SELECT count(*) FROM staff_decisions") == 0
    assert desk.ai_service.requests == []


async def test_a_manual_ticket_is_escalated_and_a_manager_answers_it(
    desk: ManualDesk, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    escalated = await act_on_ticket(
        desk.client,
        staff,
        ticket_path(desk.ticket_id, ESCALATIONS),
        {"staff_reason_codes": ["missing_case_info"]},
    )

    sent = await act_on_ticket(
        desk.client, manager, ticket_path(desk.ticket_id, REPLIES), WITHOUT_DRAFT, OTHER_KEY
    )

    assert escalated.status_code == HTTPStatus.CREATED
    assert sent.status_code == HTTPStatus.CREATED
    assert await builder.scalar(
        "SELECT jsonb_build_array(decision_type, suggestion_id, final_intent) FROM staff_decisions"
    ) == ["escalate", None, None]
    assert desk.ai_service.requests == []


@pytest.mark.parametrize(
    ("operation", "body"),
    [
        (
            PROPOSALS,
            {
                "basis": "ai_draft",
                "body": PROPOSED_TEXT,
                "suggestion_id": UNKNOWN_SUGGESTION_ID,
                "acknowledged_warning_ids": [],
            },
        ),
        (
            REPLIES,
            {
                "basis": "rejected_ai_draft",
                "body": REPLY_TEXT,
                "suggestion_id": UNKNOWN_SUGGESTION_ID,
                "staff_reason_codes": ["kb_gap"],
            },
        ),
        (
            ESCALATIONS,
            {"staff_reason_codes": ["kb_gap"], "suggestion_id": UNKNOWN_SUGGESTION_ID},
        ),
    ],
    ids=["proposal-on-a-draft", "reply-rejecting-a-draft", "escalation-naming-a-suggestion"],
)
async def test_a_manual_ticket_refuses_a_body_that_names_a_suggestion(
    desk: ManualDesk, builder: DatabaseBuilder, operation: str, body: dict[str, object]
) -> None:
    staff = await sign_in_as_support(builder)

    response = await act_on_ticket(desk.client, staff, ticket_path(desk.ticket_id, operation), body)

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.CONFLICT,
        SUGGESTION_SUPERSEDED,
    )
    assert await ticket_status(builder, desk.ticket_id) == "open"
    assert desk.ai_service.requests == []


async def test_the_customer_of_a_manual_ticket_reads_the_reply_once_it_is_sent(
    desk: ManualDesk, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    await act_on_ticket(desk.client, staff, ticket_path(desk.ticket_id, REPLIES), WITHOUT_DRAFT)

    seen = await desk.client.get(
        f"/v1/shop/tickets/{desk.ticket_id}", headers=desk.customer_headers
    )

    assert seen.json()["customer_status"] == "replied"
    assert seen.json()["reply"]["body"] == REPLY_TEXT
    assert desk.ai_service.requests == []
