"""Escalations over HTTP against PostgreSQL (`createEscalation`, then a manager's reply).

Staff escalate an `open` ticket with at least one reason code, also while a suggestion part is
pending, and the escalation records the staff decision `escalate` (ADR-0006). A manager then
sends the reply. The checks answer in the order of the contract.
"""

import asyncio
from http import HTTPStatus

import pytest

from tests.integration.application import ORIGIN_HEADERS, RunningBackend
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.tickets.console_requests import (
    DECISION_ROWS,
    ESCALATIONS,
    FORBIDDEN,
    INVALID_KEY_HEADERS,
    INVALID_KEY_IDS,
    INVALID_REQUEST,
    INVALID_TICKET_STATE,
    MESSAGE,
    NOW_TEXT,
    OTHER_KEY,
    PREDICTED_INTENT,
    REPLIES,
    STAFF_NAME,
    SUGGESTION_SUPERSEDED,
    UNKNOWN_SUGGESTION_ID,
    UNKNOWN_TICKET_ID,
    act_on_ticket,
    analysis_ready_draft_pending,
    draft_ready,
    insert_suggestion,
    key_headers,
    open_ticket,
    sign_in_as_manager,
    sign_in_as_support,
    ticket_path,
    ticket_status,
    without_fields,
)

pytestmark = pytest.mark.anyio

NOTE = "The customer asks to talk to a person."
REPLY_TEXT = "Thank you for your patience. A manager will call you today."
CASE_EXCEPTION = {"staff_reason_codes": ["case_exception"]}
NOTE_REQUIRED_DETAIL = "A note is required when staff_reason_codes contains other."


async def test_escalation_answers_201_in_the_shape_of_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    suggestion_id = await insert_suggestion(builder, ticket.ticket_id, draft_ready())
    body = {"staff_reason_codes": ["other"], "note": NOTE, "suggestion_id": suggestion_id}

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), body
    )

    assert response.status_code == HTTPStatus.CREATED
    assert without_fields(response, "escalation_id") == {
        "staff_reason_codes": ["other"],
        "note": NOTE,
        "suggestion_id": suggestion_id,
        "escalated_by": {"account_id": str(staff.account_id), "display_name": STAFF_NAME},
        "escalated_at": NOW_TEXT,
    }


async def test_escalation_moves_the_ticket_and_records_the_decision_escalate(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    suggestion_id = await insert_suggestion(builder, ticket.ticket_id, draft_ready())
    body = {"staff_reason_codes": ["case_exception"], "suggestion_id": suggestion_id}

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), body
    )

    assert response.json()["escalation_id"] == await builder.scalar(
        "SELECT escalation_id::text FROM escalations"
    )
    assert await ticket_status(builder, ticket.ticket_id) == "escalated"
    assert await builder.scalar(DECISION_ROWS) == [
        {
            "decision_type": "escalate",
            "suggestion_id": suggestion_id,
            "staff_reason_codes": ["case_exception"],
            "change_ratio": None,
            "final_intent": PREDICTED_INTENT,
            "decided_by": str(staff.account_id),
            "proposed_by": None,
            "is_proposal_changed": None,
        }
    ]


async def test_escalation_without_a_suggestion_omits_it_and_records_no_intent(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), CASE_EXCEPTION
    )

    assert "suggestion_id" not in response.json()
    assert "note" not in response.json()
    assert await builder.scalar(
        "SELECT jsonb_build_array(suggestion_id, final_intent) FROM staff_decisions"
    ) == [None, None]


async def test_staff_escalate_while_the_draft_is_pending(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, analysis_ready_draft_pending())

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), CASE_EXCEPTION
    )

    assert response.status_code == HTTPStatus.CREATED
    assert await ticket_status(builder, ticket.ticket_id) == "escalated"


async def test_workspace_shows_the_escalation_and_lets_only_a_manager_reply(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    ticket = await open_ticket(builder)
    escalation = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), CASE_EXCEPTION
    )

    for_manager = await backend.client.get(ticket_path(ticket.ticket_id), headers=manager.headers)
    for_staff = await backend.client.get(ticket_path(ticket.ticket_id), headers=staff.headers)

    assert for_manager.json()["escalation"] == escalation.json()
    assert for_manager.json()["allowed_actions"] == ["send_reply"]
    assert for_staff.json()["allowed_actions"] == []
    assert "proposal" not in for_manager.json()


async def test_a_manager_answers_an_escalated_ticket_and_it_keeps_its_escalation(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    manager = await sign_in_as_manager(builder)
    ticket = await open_ticket(builder)
    escalation = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), CASE_EXCEPTION
    )

    sent = await act_on_ticket(
        backend.client,
        manager,
        ticket_path(ticket.ticket_id, REPLIES),
        {"basis": "no_ai_draft", "body": REPLY_TEXT},
        OTHER_KEY,
    )
    closed = await backend.client.get(ticket_path(ticket.ticket_id), headers=manager.headers)

    assert sent.status_code == HTTPStatus.CREATED
    assert closed.json()["status"] == "closed"
    assert closed.json()["escalation"] == escalation.json()
    assert closed.json()["reply"] == sent.json()


async def test_staff_get_403_forbidden_when_they_reply_to_an_escalated_ticket(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), CASE_EXCEPTION
    )

    response = await act_on_ticket(
        backend.client,
        staff,
        ticket_path(ticket.ticket_id, REPLIES),
        {"basis": "no_ai_draft", "body": REPLY_TEXT},
        OTHER_KEY,
    )

    assert (response.status_code, response.json()["type"]) == (HTTPStatus.FORBIDDEN, FORBIDDEN)


async def test_other_without_a_note_returns_422_and_stores_nothing(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await act_on_ticket(
        backend.client,
        staff,
        ticket_path(ticket.ticket_id, ESCALATIONS),
        {"staff_reason_codes": ["case_exception", "other"]},
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.UNPROCESSABLE_CONTENT,
        INVALID_REQUEST,
    )
    assert response.json()["detail"] == NOTE_REQUIRED_DETAIL
    assert await builder.scalar("SELECT count(*) FROM escalations") == 0
    assert await ticket_status(builder, ticket.ticket_id) == "open"


@pytest.mark.parametrize(
    ("body", "location"),
    [
        ({"staff_reason_codes": ["kb_gap", "kb_gap"]}, "body.staff_reason_codes"),
        ({"staff_reason_codes": []}, "body.staff_reason_codes"),
        ({"staff_reason_codes": ["other"], "note": "Call\x00me"}, "body.note"),
    ],
    ids=["repeated-reason-code", "no-reason-code", "note-with-nul"],
)
async def test_body_that_breaks_the_contract_returns_422_at_its_location(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    body: dict[str, object],
    location: str,
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), body
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == (f"The request does not match the contract at: {location}.")


async def test_escalation_of_a_ticket_awaiting_approval_returns_409_invalid_ticket_state(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder, TicketSpec(message=MESSAGE, status="awaiting_approval"))

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), CASE_EXCEPTION
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.CONFLICT,
        INVALID_TICKET_STATE,
    )


async def test_escalation_on_another_suggestion_returns_409_before_the_note_rule(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, draft_ready())
    body = {"staff_reason_codes": ["other"], "suggestion_id": UNKNOWN_SUGGESTION_ID}

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, ESCALATIONS), body
    )

    assert (response.status_code, response.json()["type"]) == (
        HTTPStatus.CONFLICT,
        SUGGESTION_SUPERSEDED,
    )


async def test_repeat_with_the_same_key_returns_the_same_body_without_a_second_escalation(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    path = ticket_path(ticket.ticket_id, ESCALATIONS)
    first = await act_on_ticket(backend.client, staff, path, CASE_EXCEPTION)

    repeated = await act_on_ticket(backend.client, staff, path, CASE_EXCEPTION)

    assert (repeated.status_code, repeated.content) == (HTTPStatus.CREATED, first.content)
    assert await builder.scalar("SELECT count(*) FROM escalations") == 1
    assert await builder.scalar("SELECT count(*) FROM staff_decisions") == 1


async def test_two_concurrent_escalations_store_one_and_refuse_the_other(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    path = ticket_path(ticket.ticket_id, ESCALATIONS)

    responses = await asyncio.gather(
        act_on_ticket(backend.client, staff, path, CASE_EXCEPTION),
        act_on_ticket(backend.client, staff, path, CASE_EXCEPTION, OTHER_KEY),
    )

    created, refused = sorted(responses, key=lambda response: response.status_code)
    assert created.status_code == HTTPStatus.CREATED
    assert (refused.status_code, refused.json()["type"]) == (
        HTTPStatus.CONFLICT,
        INVALID_TICKET_STATE,
    )
    assert await builder.scalar("SELECT count(*) FROM staff_decisions") == 1


async def test_a_manager_gets_403_forbidden_and_nothing_is_stored(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    manager = await sign_in_as_manager(builder)
    ticket = await open_ticket(builder)

    response = await act_on_ticket(
        backend.client, manager, ticket_path(ticket.ticket_id, ESCALATIONS), CASE_EXCEPTION
    )

    assert (response.status_code, response.json()["type"]) == (HTTPStatus.FORBIDDEN, FORBIDDEN)
    assert await ticket_status(builder, ticket.ticket_id) == "open"


async def test_escalation_of_an_unknown_ticket_returns_404(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)

    response = await act_on_ticket(
        backend.client, staff, ticket_path(UNKNOWN_TICKET_ID, ESCALATIONS), CASE_EXCEPTION
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("key_header", INVALID_KEY_HEADERS, ids=INVALID_KEY_IDS)
async def test_escalation_with_a_missing_or_invalid_key_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, key_header: dict[str, str]
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, ESCALATIONS),
        json=CASE_EXCEPTION,
        headers={**staff.headers, **key_header},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_escalation_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, ESCALATIONS),
        json=CASE_EXCEPTION,
        headers=key_headers(ORIGIN_HEADERS),
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
