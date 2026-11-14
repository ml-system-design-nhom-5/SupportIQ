"""Guardrail: a reply reaches the customer only when staff or a manager send it (TEST-26).

FR-04: a reply proposal and an escalation never reach the customer; only `sendReply` does.
FR-06: staff never send on a ticket that requires authority, waits for approval, or was
escalated; a manager sends it. SEC-38: a proposal with a placeholder is refused and stored
nowhere. The tickets have no suggestion, so ai-service is never called.
"""

from dataclasses import dataclass
from http import HTTPStatus

import pytest

from tests.integration.application import RunningBackend, session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder, TicketSpec

pytestmark = pytest.mark.anyio

CONSOLE_TICKETS = "/v1/console/tickets"
SHOP_TICKETS = "/v1/shop/tickets"
KEY = "00000000-0000-4000-8000-000000000001"
OTHER_KEY = "00000000-0000-4000-8000-000000000002"
THIRD_KEY = "00000000-0000-4000-8000-000000000003"
PROPOSED_TEXT = "We have approved a refund of the full amount to your card."
REPLY_TEXT = "Your parcel left our warehouse yesterday."
AUTHORITY_REQUIRED = "urn:supportiq:problem:authority-required"
FORBIDDEN = "urn:supportiq:problem:forbidden"
INVALID_REQUEST = "urn:supportiq:problem:invalid-request"


@dataclass(frozen=True, slots=True)
class Desk:
    """A customer's open ticket and the sessions of the three roles that touch it.

    Attributes:
        ticket_id: The ticket.
        customer: The headers of the customer's session.
        staff: The headers of a staff session.
        manager: The headers of a manager session.
        manager_id: The account of the manager.
    """

    ticket_id: str
    customer: dict[str, str]
    staff: dict[str, str]
    manager: dict[str, str]
    manager_id: object


async def build_desk(builder: DatabaseBuilder, *, is_authority_required: bool) -> Desk:
    customer_account, customer_id = await builder.customer_account()
    order_id = await builder.order_of_one_product(customer_id)
    ticket_id = await builder.ticket(
        customer_id, order_id, TicketSpec(is_authority_required=is_authority_required)
    )
    staff = await builder.account(AccountSpec("staff"))
    manager = await builder.account(AccountSpec("manager"))
    return Desk(
        ticket_id=ticket_id,
        customer=session_headers(await builder.session(customer_account, "customer")),
        staff=session_headers(await builder.session(staff, "staff")),
        manager=session_headers(await builder.session(manager, "manager")),
        manager_id=manager,
    )


async def act(
    backend: RunningBackend, desk: Desk, headers: dict[str, str], operation: str, body: object
) -> tuple[HTTPStatus, dict[str, object]]:
    response = await backend.client.post(
        f"{CONSOLE_TICKETS}/{desk.ticket_id}/{operation}",
        json=body,
        headers={**headers, "Idempotency-Key": THIRD_KEY if headers is desk.manager else KEY},
    )
    return HTTPStatus(response.status_code), response.json()


async def send_as_staff(backend: RunningBackend, desk: Desk) -> tuple[HTTPStatus, object]:
    response = await backend.client.post(
        f"{CONSOLE_TICKETS}/{desk.ticket_id}/replies",
        json={"basis": "no_ai_draft", "body": REPLY_TEXT},
        headers={**desk.staff, "Idempotency-Key": OTHER_KEY},
    )
    return HTTPStatus(response.status_code), response.json()["type"]


async def shop_view(backend: RunningBackend, desk: Desk) -> str:
    response = await backend.client.get(f"{SHOP_TICKETS}/{desk.ticket_id}", headers=desk.customer)
    assert response.status_code == HTTPStatus.OK
    return response.text


async def test_a_proposal_reaches_the_customer_only_when_a_manager_sends_it(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    desk = await build_desk(builder, is_authority_required=True)
    proposal = {"basis": "no_ai_draft", "body": PROPOSED_TEXT}

    before_proposal = await send_as_staff(backend, desk)
    proposed_status, proposed = await act(backend, desk, desk.staff, "reply-proposals", proposal)
    after_proposal = await send_as_staff(backend, desk)
    seen_while_waiting = await shop_view(backend, desk)
    sent_status, _ = await act(
        backend,
        desk,
        desk.manager,
        "replies",
        {
            "basis": "reply_proposal",
            "body": PROPOSED_TEXT,
            "proposal_id": proposed["proposal_id"],
        },
    )

    assert before_proposal == (HTTPStatus.FORBIDDEN, AUTHORITY_REQUIRED)
    assert proposed_status == HTTPStatus.CREATED
    assert after_proposal == (HTTPStatus.FORBIDDEN, FORBIDDEN)
    assert PROPOSED_TEXT not in seen_while_waiting
    assert sent_status == HTTPStatus.CREATED
    assert PROPOSED_TEXT in await shop_view(backend, desk)
    assert (
        await builder.scalar(
            "SELECT sent_by_account_id FROM replies WHERE ticket_id = :ticket_id",
            ticket_id=desk.ticket_id,
        )
        == desk.manager_id
    )


async def test_an_escalated_ticket_reaches_the_customer_only_when_a_manager_sends_it(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    desk = await build_desk(builder, is_authority_required=False)

    escalated_status, _ = await act(
        backend, desk, desk.staff, "escalations", {"staff_reason_codes": ["case_exception"]}
    )
    after_escalation = await send_as_staff(backend, desk)
    seen_while_escalated = await shop_view(backend, desk)
    sent_status, _ = await act(
        backend, desk, desk.manager, "replies", {"basis": "no_ai_draft", "body": REPLY_TEXT}
    )

    assert escalated_status == HTTPStatus.CREATED
    assert after_escalation == (HTTPStatus.FORBIDDEN, FORBIDDEN)
    assert REPLY_TEXT not in seen_while_escalated
    assert sent_status == HTTPStatus.CREATED
    assert REPLY_TEXT in await shop_view(backend, desk)


async def test_a_proposal_with_a_placeholder_is_refused_and_stored_nowhere(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    desk = await build_desk(builder, is_authority_required=True)
    proposal = {"basis": "no_ai_draft", "body": "We wrote to [EMAIL_1] about your refund."}

    status, problem = await act(backend, desk, desk.staff, "reply-proposals", proposal)

    assert (status, problem["type"]) == (HTTPStatus.UNPROCESSABLE_CONTENT, INVALID_REQUEST)
    assert await builder.scalar("SELECT count(*) FROM reply_proposals") == 0
    assert (
        await builder.scalar(
            "SELECT status FROM tickets WHERE ticket_id = :ticket_id", ticket_id=desk.ticket_id
        )
        == "open"
    )
