"""Submitting reply proposals over HTTP against PostgreSQL (`createReplyProposal`).

Staff propose the reply of a ticket, which then awaits a manager's approval; a proposal never
reaches the customer (FR-04). The body is read once, at the boundary, and the checks answer
in the order of the contract.
"""

import asyncio
from http import HTTPStatus

import pytest

from tests.integration.application import ORIGIN_HEADERS, RunningBackend
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.tickets.console_requests import (
    DRAFT_TEXT,
    FORBIDDEN,
    INVALID_KEY_HEADERS,
    INVALID_KEY_IDS,
    INVALID_REQUEST,
    INVALID_TICKET_STATE,
    MESSAGE,
    NOW_TEXT,
    OTHER_KEY,
    PROPOSALS,
    STAFF_NAME,
    SUGGESTION_PENDING,
    SUGGESTION_SUPERSEDED,
    UNKNOWN_PROPOSAL_ID,
    UNKNOWN_SUGGESTION_ID,
    UNKNOWN_TICKET_ID,
    act_on_ticket,
    analysis_ready_draft_pending,
    insert_suggestion,
    key_headers,
    open_ticket,
    sign_in_as_manager,
    sign_in_as_support,
    ticket_path,
    ticket_status,
    without_fields,
)
from tests.integration.tickets.proposal_requests import (
    NOTE,
    OWN_TEXT,
    WITHOUT_DRAFT,
    on_the_draft,
    on_the_proposal,
    propose,
    ticket_with_a_ready_draft,
)

pytestmark = pytest.mark.anyio


async def test_proposal_on_the_draft_answers_201_in_the_shape_of_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket, suggestion_id = await ticket_with_a_ready_draft(builder, is_authority_required=True)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, PROPOSALS), on_the_draft(suggestion_id)
    )

    assert response.status_code == HTTPStatus.CREATED
    assert without_fields(response, "proposal_id") == {
        "basis": "ai_draft",
        "body": DRAFT_TEXT,
        "suggestion_id": suggestion_id,
        "staff_reason_codes": [],
        "proposed_by": {"account_id": str(staff.account_id), "display_name": STAFF_NAME},
        "created_at": NOW_TEXT,
    }


async def test_proposal_without_a_draft_answers_201_in_the_shape_of_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, PROPOSALS), WITHOUT_DRAFT
    )

    assert response.status_code == HTTPStatus.CREATED
    assert without_fields(response, "proposal_id") == {
        "basis": "no_ai_draft",
        "body": OWN_TEXT,
        "staff_reason_codes": [],
        "proposed_by": {"account_id": str(staff.account_id), "display_name": STAFF_NAME},
        "created_at": NOW_TEXT,
    }


async def test_proposal_that_rejects_the_draft_returns_its_reasons_and_note(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket, suggestion_id = await ticket_with_a_ready_draft(builder, is_authority_required=False)
    body = {
        "basis": "rejected_ai_draft",
        "body": OWN_TEXT,
        "suggestion_id": suggestion_id,
        "staff_reason_codes": ["other", "kb_gap"],
        "note": NOTE,
    }

    proposal = await propose(backend, staff, ticket.ticket_id, body)

    assert (proposal["staff_reason_codes"], proposal["note"]) == (["other", "kb_gap"], NOTE)


async def test_proposal_id_names_the_stored_proposal_and_the_ticket_awaits_approval(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    proposal = await propose(backend, staff, ticket.ticket_id, WITHOUT_DRAFT)

    assert proposal["proposal_id"] == await builder.scalar(
        "SELECT proposal_id::text FROM reply_proposals"
    )
    assert await ticket_status(builder, ticket.ticket_id) == "awaiting_approval"


async def test_repeat_with_the_same_key_returns_the_same_body_without_a_second_proposal(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    path = ticket_path(ticket.ticket_id, PROPOSALS)
    first = await act_on_ticket(backend.client, staff, path, WITHOUT_DRAFT)

    repeated = await act_on_ticket(backend.client, staff, path, WITHOUT_DRAFT)

    assert (repeated.status_code, repeated.content) == (HTTPStatus.CREATED, first.content)
    assert await builder.scalar("SELECT count(*) FROM reply_proposals") == 1
    assert (
        await builder.scalar(
            "SELECT count(*) FROM audit_log_entries WHERE event_type = 'reply_proposal.submitted'"
        )
        == 1
    )


async def test_two_concurrent_proposals_store_one_and_refuse_the_other(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    path = ticket_path(ticket.ticket_id, PROPOSALS)

    responses = await asyncio.gather(
        act_on_ticket(backend.client, staff, path, WITHOUT_DRAFT),
        act_on_ticket(backend.client, staff, path, WITHOUT_DRAFT, OTHER_KEY),
    )

    created, refused = sorted(responses, key=lambda response: response.status_code)
    assert created.status_code == HTTPStatus.CREATED
    assert (refused.status_code, refused.json()["type"]) == (
        HTTPStatus.CONFLICT,
        INVALID_TICKET_STATE,
    )
    assert await builder.scalar("SELECT count(*) FROM reply_proposals") == 1


async def test_a_manager_gets_403_forbidden_and_nothing_is_stored(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    manager = await sign_in_as_manager(builder)
    ticket = await open_ticket(builder)

    response = await act_on_ticket(
        backend.client, manager, ticket_path(ticket.ticket_id, PROPOSALS), WITHOUT_DRAFT
    )

    assert (response.status_code, response.json()["type"]) == (HTTPStatus.FORBIDDEN, FORBIDDEN)
    assert await ticket_status(builder, ticket.ticket_id) == "open"


async def test_proposal_on_an_escalated_ticket_returns_409_invalid_ticket_state(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder, TicketSpec(message=MESSAGE, status="escalated"))

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, PROPOSALS), WITHOUT_DRAFT
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.CONFLICT,
        INVALID_TICKET_STATE,
    )


async def test_proposal_while_the_draft_is_pending_returns_409_suggestion_pending(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, analysis_ready_draft_pending())

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, PROPOSALS), WITHOUT_DRAFT
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.CONFLICT,
        SUGGESTION_PENDING,
    )


async def test_proposal_on_another_suggestion_returns_409_suggestion_superseded(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket, _suggestion_id = await ticket_with_a_ready_draft(builder, is_authority_required=False)

    response = await act_on_ticket(
        backend.client,
        staff,
        ticket_path(ticket.ticket_id, PROPOSALS),
        on_the_draft(UNKNOWN_SUGGESTION_ID),
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.CONFLICT,
        SUGGESTION_SUPERSEDED,
    )


async def test_proposal_with_a_placeholder_returns_422_and_stores_nothing(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    body = {"basis": "no_ai_draft", "body": "We wrote to [EMAIL_1] about your refund."}

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, PROPOSALS), body
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.UNPROCESSABLE_CONTENT,
        INVALID_REQUEST,
    )
    assert await builder.scalar("SELECT count(*) FROM reply_proposals") == 0


async def test_proposal_with_a_repeated_reason_code_returns_422_at_its_location(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket, suggestion_id = await ticket_with_a_ready_draft(builder, is_authority_required=False)
    body = {
        "basis": "rejected_ai_draft",
        "body": OWN_TEXT,
        "suggestion_id": suggestion_id,
        "staff_reason_codes": ["kb_gap", "kb_gap"],
    }

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, PROPOSALS), body
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == (
        "The request does not match the contract at: body.staff_reason_codes."
    )


async def test_proposal_with_the_basis_reply_proposal_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    body = on_the_proposal(UNKNOWN_PROPOSAL_ID)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, PROPOSALS), body
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.UNPROCESSABLE_CONTENT,
        INVALID_REQUEST,
    )


async def test_proposal_for_an_unknown_ticket_returns_404(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(UNKNOWN_TICKET_ID, PROPOSALS), WITHOUT_DRAFT
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("key_header", INVALID_KEY_HEADERS, ids=INVALID_KEY_IDS)
async def test_proposal_with_a_missing_or_invalid_key_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, key_header: dict[str, str]
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, PROPOSALS),
        json=WITHOUT_DRAFT,
        headers={**staff.headers, **key_header},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_proposal_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, PROPOSALS),
        json=WITHOUT_DRAFT,
        headers=key_headers(ORIGIN_HEADERS),
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
