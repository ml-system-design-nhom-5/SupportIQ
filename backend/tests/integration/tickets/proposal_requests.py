"""What the tests of reply proposals share: proposal bodies and tickets with a ready draft."""

from tests.integration.application import RunningBackend
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.tickets.console_requests import (
    DRAFT_TEXT,
    MESSAGE,
    PROPOSALS,
    TICKET_CREATED_AT,
    WARNING_ID,
    ConsoleTicket,
    SupportSession,
    act_on_ticket,
    draft_ready,
    insert_suggestion,
    open_ticket,
    ticket_path,
)

OWN_TEXT = "A manager will confirm the refund of your order today."
NOTE = "The customer asked for the manager by name."
WITHOUT_DRAFT = {"basis": "no_ai_draft", "body": OWN_TEXT}


def on_the_draft(suggestion_id: str, body: str = DRAFT_TEXT) -> dict[str, object]:
    return {
        "basis": "ai_draft",
        "body": body,
        "suggestion_id": suggestion_id,
        "acknowledged_warning_ids": [WARNING_ID],
    }


def on_the_proposal(proposal_id: str, body: str = OWN_TEXT) -> dict[str, object]:
    """Return the body of a manager's reply that sends the proposal that it names."""
    return {"basis": "reply_proposal", "body": body, "proposal_id": proposal_id}


async def ticket_with_a_ready_draft(
    builder: DatabaseBuilder, *, is_authority_required: bool
) -> tuple[ConsoleTicket, str]:
    spec = TicketSpec(
        message=MESSAGE,
        created_at=TICKET_CREATED_AT,
        is_authority_required=is_authority_required,
    )
    ticket = await open_ticket(builder, spec)
    suggestion_id = await insert_suggestion(builder, ticket.ticket_id, draft_ready())
    return ticket, suggestion_id


async def propose(
    backend: RunningBackend, staff: SupportSession, ticket_id: str, body: object
) -> dict[str, object]:
    response = await act_on_ticket(backend.client, staff, ticket_path(ticket_id, PROPOSALS), body)
    return response.json()
