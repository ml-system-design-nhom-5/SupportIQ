"""What the tests of reply proposals share: proposal bodies and tickets with a ready draft."""

from tests.integration.application import RunningBackend
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.database import WorkerDatabase
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
TICKET_STATUS = "SELECT status FROM tickets WHERE ticket_id = :ticket_id"


def on_the_draft(suggestion_id: str, body: str = DRAFT_TEXT) -> dict[str, object]:
    return {
        "basis": "ai_draft",
        "body": body,
        "suggestion_id": suggestion_id,
        "acknowledged_warning_ids": [WARNING_ID],
    }


async def ticket_with_a_ready_draft(
    builder: DatabaseBuilder, worker_database: WorkerDatabase, *, is_authority_required: bool
) -> tuple[ConsoleTicket, str]:
    spec = TicketSpec(
        message=MESSAGE,
        created_at=TICKET_CREATED_AT,
        is_authority_required=is_authority_required,
    )
    ticket = await open_ticket(builder, spec)
    suggestion_id = await insert_suggestion(
        worker_database, builder, ticket.ticket_id, draft_ready()
    )
    return ticket, suggestion_id


async def propose(
    backend: RunningBackend, staff: SupportSession, ticket_id: str, body: object
) -> dict[str, object]:
    response = await act_on_ticket(backend.client, staff, ticket_path(ticket_id, PROPOSALS), body)
    return response.json()


async def ticket_status(builder: DatabaseBuilder, ticket_id: str) -> object:
    return await builder.scalar(TICKET_STATUS, ticket_id=ticket_id)
