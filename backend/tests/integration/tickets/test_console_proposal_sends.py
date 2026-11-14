"""Sending reply proposals over HTTP against PostgreSQL (`sendReply` with `reply_proposal`).

Staff propose the reply of a ticket that requires authority, and a manager sends it; the
decision row then holds both accounts (contracts v1 design, Recorded decision; FR-06). The
customer sees no proposal text until a manager sends it (FR-04).
"""

from http import HTTPStatus

import pytest

from tests.integration.application import RunningBackend
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.database import WorkerDatabase
from tests.integration.tickets.console_requests import (
    DECISION_ROWS,
    DRAFT_TEXT,
    FORBIDDEN,
    MANAGER_NAME,
    MESSAGE,
    NOW_TEXT,
    OTHER_KEY,
    PREDICTED_INTENT,
    REPLIES,
    act_on_ticket,
    open_ticket,
    sign_in_as_manager,
    sign_in_as_support,
    ticket_path,
    without_fields,
)
from tests.integration.tickets.proposal_requests import (
    OWN_TEXT,
    WITHOUT_DRAFT,
    on_the_draft,
    propose,
    ticket_status,
    ticket_with_a_ready_draft,
)
from tests.integration.tickets.shop_requests import sign_in_as_new_customer

pytestmark = pytest.mark.anyio

UNKNOWN_PROPOSAL_ID = "00000000-0000-4000-8000-0000000000f3"
AUTHORITY_REQUIRED = "urn:supportiq:problem:authority-required"


async def test_workspace_shows_the_proposal_and_lets_only_a_manager_send_it(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    ticket = await open_ticket(builder)
    proposal = await propose(backend, staff, ticket.ticket_id, WITHOUT_DRAFT)

    for_manager = await backend.client.get(ticket_path(ticket.ticket_id), headers=manager.headers)
    for_staff = await backend.client.get(ticket_path(ticket.ticket_id), headers=staff.headers)

    assert for_manager.json()["proposal"] == proposal
    assert for_manager.json()["allowed_actions"] == ["send_reply"]
    assert for_staff.json()["proposal"] == proposal
    assert for_staff.json()["allowed_actions"] == []
    assert "escalation" not in for_manager.json()


async def test_staff_get_403_forbidden_when_they_reply_to_an_awaiting_ticket(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    await propose(backend, staff, ticket.ticket_id, WITHOUT_DRAFT)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, REPLIES), WITHOUT_DRAFT, OTHER_KEY
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["type"] == FORBIDDEN
    assert await builder.scalar("SELECT count(*) FROM replies") == 0


async def test_authority_needs_a_proposal_that_a_manager_sends_with_both_accounts_recorded(
    backend: RunningBackend, builder: DatabaseBuilder, worker_database: WorkerDatabase
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    ticket, suggestion_id = await ticket_with_a_ready_draft(
        builder, worker_database, is_authority_required=True
    )
    path = ticket_path(ticket.ticket_id, REPLIES)

    refused = await act_on_ticket(backend.client, staff, path, on_the_draft(suggestion_id))
    proposal = await propose(backend, staff, ticket.ticket_id, on_the_draft(suggestion_id))
    sent = await act_on_ticket(
        backend.client,
        manager,
        path,
        {"basis": "reply_proposal", "body": DRAFT_TEXT, "proposal_id": proposal["proposal_id"]},
        OTHER_KEY,
    )

    assert (refused.status_code, refused.json()["type"]) == (
        HTTPStatus.FORBIDDEN,
        AUTHORITY_REQUIRED,
    )
    assert sent.status_code == HTTPStatus.CREATED
    assert await ticket_status(builder, ticket.ticket_id) == "closed"
    assert await builder.scalar(DECISION_ROWS) == [
        {
            "decision_type": "approve",
            "suggestion_id": suggestion_id,
            "staff_reason_codes": [],
            "change_ratio": 0,
            "final_intent": PREDICTED_INTENT,
            "decided_by": str(manager.account_id),
            "proposed_by": str(staff.account_id),
            "is_proposal_changed": False,
        }
    ]


async def test_reply_from_a_proposal_answers_201_in_the_shape_of_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder, worker_database: WorkerDatabase
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    ticket, suggestion_id = await ticket_with_a_ready_draft(
        builder, worker_database, is_authority_required=True
    )
    proposal = await propose(backend, staff, ticket.ticket_id, on_the_draft(suggestion_id))

    response = await act_on_ticket(
        backend.client,
        manager,
        ticket_path(ticket.ticket_id, REPLIES),
        {"basis": "reply_proposal", "body": OWN_TEXT, "proposal_id": proposal["proposal_id"]},
        OTHER_KEY,
    )

    assert without_fields(response, "reply_id") == {
        "basis": "reply_proposal",
        "body": OWN_TEXT,
        "suggestion_id": suggestion_id,
        "proposal_id": proposal["proposal_id"],
        "sent_by": {"account_id": str(manager.account_id), "display_name": MANAGER_NAME},
        "sent_at": NOW_TEXT,
    }
    assert await builder.scalar("SELECT is_proposal_changed FROM staff_decisions") is True


async def test_closed_workspace_keeps_the_proposal_next_to_the_reply(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    ticket = await open_ticket(builder)
    proposal = await propose(backend, staff, ticket.ticket_id, WITHOUT_DRAFT)
    sent = await act_on_ticket(
        backend.client,
        manager,
        ticket_path(ticket.ticket_id, REPLIES),
        {"basis": "reply_proposal", "body": OWN_TEXT, "proposal_id": proposal["proposal_id"]},
        OTHER_KEY,
    )

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=manager.headers)

    assert response.json()["proposal"] == proposal
    assert response.json()["reply"] == sent.json()
    assert response.json()["allowed_actions"] == []


async def test_customer_sees_no_proposal_text_until_a_manager_sends_it(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    customer_id, customer_headers = await sign_in_as_new_customer(builder)
    order_id = await builder.order_of_one_product(customer_id)
    ticket_id = await builder.ticket(customer_id, order_id, TicketSpec(message=MESSAGE))
    await propose(backend, staff, ticket_id, WITHOUT_DRAFT)

    response = await backend.client.get(f"/v1/shop/tickets/{ticket_id}", headers=customer_headers)

    assert response.json()["customer_status"] == "received"
    assert "reply" not in response.json()
    assert OWN_TEXT not in response.text


async def test_reply_on_another_proposal_returns_422_and_sends_nothing(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    ticket = await open_ticket(builder)
    await propose(backend, staff, ticket.ticket_id, WITHOUT_DRAFT)

    response = await act_on_ticket(
        backend.client,
        manager,
        ticket_path(ticket.ticket_id, REPLIES),
        {"basis": "reply_proposal", "body": OWN_TEXT, "proposal_id": UNKNOWN_PROPOSAL_ID},
        OTHER_KEY,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == (
        "The basis reply_proposal is not valid with a proposal_id that is not the proposal of"
        " the ticket."
    )
    assert await builder.scalar("SELECT count(*) FROM replies") == 0
