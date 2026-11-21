"""Escalations: staff move a ticket to the manager queue (contracts v1 design, ADR-0006).

The AI only recommends an escalation; this staff action decides it. A staff note is
Confidential, so the classes that hold one have no generated `repr` (LOG-29).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import NewType
from uuid import UUID

from app.accounts import AccountId
from app.suggestions import SuggestionId
from app.tickets.domain.replies import validate_staff_note
from app.tickets.domain.reply_requests import StaffReasonCode
from app.tickets.domain.tickets import TicketId

EscalationId = NewType("EscalationId", UUID)


@dataclass(frozen=True, slots=True, repr=False)
class EscalationRequest:
    """Why staff escalate a ticket (contract `CreateEscalationRequest`).

    Attributes:
        staff_reason_codes: The reasons, at least one, without repeats.
        note: A note for the record, required with `other`.
        suggestion_id: The current suggestion that staff saw, when they name it.
    """

    staff_reason_codes: tuple[StaffReasonCode, ...]
    note: str | None
    suggestion_id: SuggestionId | None


@dataclass(frozen=True, slots=True, repr=False)
class Escalation:
    """An escalation as stored and as the console shows it; inserted once, never updated.

    Attributes:
        escalation_id: The identifier.
        ticket_id: The ticket, `escalated` from then on until a manager sends its reply.
        request: Why staff escalated.
        escalated_by: The staff member who escalated.
        escalated_at: When the ticket was escalated.
    """

    escalation_id: EscalationId
    ticket_id: TicketId
    request: EscalationRequest
    escalated_by: AccountId
    escalated_at: datetime


def validate_escalation_body(request: EscalationRequest) -> None:
    """Run step 8 of the check order of `createEscalation`: the body rules.

    Args:
        request: The body of the request.

    Raises:
        NoteRequiredError: `other` without a note, so the reason would not be recorded.
    """
    validate_staff_note(request.staff_reason_codes, request.note)
