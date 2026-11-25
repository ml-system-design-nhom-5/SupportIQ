"""Correcting the intent over HTTP against PostgreSQL (`createSuggestion`).

The application runs without the claim loop, so the new suggestion stays pending.
"""

from http import HTTPStatus

import pytest

from tests.integration.application import ORIGIN_HEADERS, RunningBackend
from tests.integration.builders import DatabaseBuilder
from tests.integration.tickets.console_requests import (
    CORRECTED_INTENT,
    INVALID_KEY_HEADERS,
    INVALID_KEY_IDS,
    NOW_TEXT,
    UNKNOWN_TICKET_ID,
    analysis_ready_draft_pending,
    insert_suggestion,
    key_headers,
    open_ticket,
    sign_in_as_support,
    ticket_path,
    without_fields,
)

pytestmark = pytest.mark.anyio

SUGGESTIONS = "/suggestions"
CORRECTION = {"intent_override": CORRECTED_INTENT}


async def test_intent_correction_answers_202_with_the_new_pending_suggestion(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, analysis_ready_draft_pending())

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, SUGGESTIONS), json=CORRECTION, headers=key_headers(headers)
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert without_fields(response, "suggestion_id", "trace_id") == {
        "trigger": "intent_override",
        "intent_override": CORRECTED_INTENT,
        "created_at": NOW_TEXT,
        "analysis": {"analysis_status": "pending"},
        "draft": {"draft_status": "pending"},
    }


async def test_new_suggestion_becomes_the_current_one_of_the_ticket(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, analysis_ready_draft_pending())

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, SUGGESTIONS), json=CORRECTION, headers=key_headers(headers)
    )

    current = await builder.scalar(
        "SELECT current_suggestion_id::text FROM tickets WHERE ticket_id = :ticket_id",
        ticket_id=ticket.ticket_id,
    )
    assert response.json()["suggestion_id"] == current


async def test_repeated_correction_with_the_same_key_returns_the_original_response(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    await insert_suggestion(builder, ticket.ticket_id, analysis_ready_draft_pending())
    path = ticket_path(ticket.ticket_id, SUGGESTIONS)
    first = await backend.client.post(path, json=CORRECTION, headers=key_headers(headers))

    repeated = await backend.client.post(path, json=CORRECTION, headers=key_headers(headers))

    assert repeated.status_code == HTTPStatus.ACCEPTED
    assert repeated.content == first.content


@pytest.mark.parametrize("key_header", INVALID_KEY_HEADERS, ids=INVALID_KEY_IDS)
async def test_missing_or_invalid_key_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, key_header: dict[str, str]
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, SUGGESTIONS),
        json=CORRECTION,
        headers={**headers, **key_header},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"intent_override": "not_an_intent"}', b'{"extra": true}'],
    ids=["not-json", "array", "unknown-intent", "unknown-field"],
)
async def test_body_outside_the_contract_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, body: bytes
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, SUGGESTIONS), content=body, headers=key_headers(headers)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_correction_of_an_unknown_ticket_returns_404(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers

    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, SUGGESTIONS), json=CORRECTION, headers=key_headers(headers)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_correction_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, SUGGESTIONS),
        json=CORRECTION,
        headers=key_headers(ORIGIN_HEADERS),
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
