"""Sending a reply over HTTP against PostgreSQL (`sendReply`): what it answers and refuses.

The body is read once, at the boundary (CODE-32): a text that PostgreSQL cannot store, or a
repeated item of an array that the contract marks `uniqueItems: true`, gets `422` at its
location before any ticket check (CON-02). A refused request stores no idempotency record, so
the same key runs again as a new request (ERR-15).
"""

from http import HTTPStatus

import pytest

from tests.integration.application import ORIGIN_HEADERS, RunningBackend
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.tickets.console_requests import (
    DRAFT_TEXT,
    INVALID_KEY_HEADERS,
    INVALID_KEY_IDS,
    INVALID_REQUEST,
    NOW_TEXT,
    REPLIES,
    STAFF_NAME,
    SUGGESTION_PENDING,
    UNKNOWN_TICKET_ID,
    WARNING_ID,
    act_on_ticket,
    analysis_ready_draft_pending,
    complete_draft,
    count_replies,
    draft_ready,
    insert_suggestion,
    key_headers,
    open_ticket,
    sign_in_as_support,
    ticket_path,
    without_fields,
)
from tests.integration.tickets.proposal_requests import on_the_draft

pytestmark = pytest.mark.anyio

REPLY_TEXT = "Your parcel left our warehouse yesterday."
NOT_STORABLE_TEXT = "Your parcel\x00left"
PLACEHOLDER_DETAIL = (
    "The body contains a placeholder. Replace it with the text that the customer should read."
)
REPLY_WITHOUT_DRAFT = {"basis": "no_ai_draft", "body": REPLY_TEXT}
# The body is refused before any check of the ticket reads the suggestion ID.
UNCHECKED_SUGGESTION_ID = "00000000-0000-4000-8000-000000000003"
IDEMPOTENCY_RECORDS = "SELECT count(*) FROM idempotency_records"


def contract_detail(location: str) -> str:
    return f"The request does not match the contract at: {location}."


async def test_reply_without_a_draft_answers_201_in_the_shape_of_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, REPLIES),
        json=REPLY_WITHOUT_DRAFT,
        headers=key_headers(staff.headers),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert without_fields(response, "reply_id") == {
        "basis": "no_ai_draft",
        "body": REPLY_TEXT,
        "sent_by": {"account_id": str(staff.account_id), "display_name": STAFF_NAME},
        "sent_at": NOW_TEXT,
    }


async def test_reply_id_names_the_stored_reply(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, REPLIES),
        json=REPLY_WITHOUT_DRAFT,
        headers=key_headers(staff.headers),
    )

    assert response.json()["reply_id"] == await builder.scalar("SELECT reply_id::text FROM replies")


async def test_reply_on_the_draft_names_its_suggestion(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    suggestion_id = await insert_suggestion(builder, ticket.ticket_id, draft_ready())

    response = await act_on_ticket(
        backend.client, staff, ticket_path(ticket.ticket_id, REPLIES), on_the_draft(suggestion_id)
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["basis"] == "ai_draft"
    assert response.json()["suggestion_id"] == suggestion_id


async def test_a_key_refused_while_the_draft_is_pending_sends_once_the_draft_is_ready(
    backend: RunningBackend, builder: DatabaseBuilder, worker_database: WorkerDatabase
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    suggestion_id = await insert_suggestion(
        builder, ticket.ticket_id, analysis_ready_draft_pending()
    )
    path = ticket_path(ticket.ticket_id, REPLIES)

    refused = await act_on_ticket(backend.client, staff, path, on_the_draft(suggestion_id))
    records_after_refusal = await builder.scalar(IDEMPOTENCY_RECORDS)
    await complete_draft(worker_database, suggestion_id)
    sent = await act_on_ticket(backend.client, staff, path, on_the_draft(suggestion_id))

    assert (refused.status_code, refused.json()["type"]) == (
        HTTPStatus.CONFLICT,
        SUGGESTION_PENDING,
    )
    assert records_after_refusal == 0
    assert sent.status_code == HTTPStatus.CREATED
    assert sent.json()["suggestion_id"] == suggestion_id
    assert await count_replies(builder) == 1


@pytest.mark.parametrize(
    ("body", "location"),
    [
        (
            {
                "basis": "ai_draft",
                "body": DRAFT_TEXT,
                "acknowledged_warning_ids": [WARNING_ID, WARNING_ID],
            },
            "body.acknowledged_warning_ids",
        ),
        (
            {
                "basis": "ai_draft",
                "body": REPLY_TEXT,
                "acknowledged_warning_ids": [WARNING_ID],
                "staff_reason_codes": ["tone_or_clarity", "tone_or_clarity"],
            },
            "body.staff_reason_codes",
        ),
        (
            {
                "basis": "rejected_ai_draft",
                "body": REPLY_TEXT,
                "staff_reason_codes": ["wrong_intent", "wrong_intent"],
            },
            "body.staff_reason_codes",
        ),
    ],
    ids=["warning-ids", "edit-reason-codes", "reject-reason-codes"],
)
async def test_repeated_item_of_a_unique_array_returns_422_and_sends_nothing(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    body: dict[str, object],
    location: str,
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)
    suggestion_id = await insert_suggestion(builder, ticket.ticket_id, draft_ready())

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, REPLIES),
        json={**body, "suggestion_id": suggestion_id},
        headers=key_headers(staff.headers),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["type"] == INVALID_REQUEST
    assert response.json()["detail"] == contract_detail(location)
    assert await count_replies(builder) == 0


@pytest.mark.parametrize(
    ("body", "location"),
    [
        ({"basis": "no_ai_draft", "body": NOT_STORABLE_TEXT}, "body.body"),
        (
            {
                "basis": "rejected_ai_draft",
                "body": REPLY_TEXT,
                "suggestion_id": UNCHECKED_SUGGESTION_ID,
                "staff_reason_codes": ["other"],
                "note": NOT_STORABLE_TEXT,
            },
            "body.note",
        ),
    ],
    ids=["body-with-nul", "note-with-nul"],
)
async def test_field_that_backend_cannot_read_returns_422_at_its_location(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    body: dict[str, object],
    location: str,
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, REPLIES), json=body, headers=key_headers(staff.headers)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == contract_detail(location)


async def test_body_with_a_placeholder_returns_422_and_sends_nothing(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, REPLIES),
        json={"basis": "no_ai_draft", "body": "Hello [NAME_1], your parcel is on its way."},
        headers=key_headers(staff.headers),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == PLACEHOLDER_DETAIL
    assert await count_replies(builder) == 0


@pytest.mark.parametrize("key_header", INVALID_KEY_HEADERS, ids=INVALID_KEY_IDS)
async def test_missing_or_invalid_key_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, key_header: dict[str, str]
) -> None:
    staff = await sign_in_as_support(builder)
    ticket = await open_ticket(builder)

    response = await backend.client.post(
        ticket_path(ticket.ticket_id, REPLIES),
        json=REPLY_WITHOUT_DRAFT,
        headers={**staff.headers, **key_header},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_reply_to_an_unknown_ticket_returns_404(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    staff = await sign_in_as_support(builder)

    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, REPLIES),
        json=REPLY_WITHOUT_DRAFT,
        headers=key_headers(staff.headers),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_reply_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.post(
        ticket_path(UNKNOWN_TICKET_ID, REPLIES),
        json=REPLY_WITHOUT_DRAFT,
        headers=key_headers(ORIGIN_HEADERS),
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
