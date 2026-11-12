"""Tickets as the console sees them: the state machine, the check order, and allowed actions.

The checks follow the check order of the backend ticket workflow design and stop at the first
failure, so a request that breaks two rules always gets the same answer. `allowed_actions` is
computed by the same rules, so the console never offers an action that a check would refuse.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from supportiq_backend.accounts import CustomerId, ForbiddenRoleError, SupportRole
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform import BackendError, ErrorCode
from supportiq_backend.suggestions import (
    InvalidTicketStateError,
    Suggestion,
    SuggestionId,
    SuggestionPendingError,
    SuggestionSupersededError,
)
from supportiq_backend.tickets.domain.tickets import HandlingMode, TicketId, TicketStatus

# How many characters of the message a ticket summary shows (backend contract 1.2.0).
MESSAGE_EXCERPT_LENGTH = 160


class TicketAction(StrEnum):
    """An action of the ticket workspace, as `allowed_actions` names it."""

    SEND_REPLY = "send_reply"
    SUBMIT_REPLY_PROPOSAL = "submit_reply_proposal"
    ESCALATE = "escalate"
    CORRECT_INTENT = "correct_intent"
    RETRY_SUGGESTION = "retry_suggestion"


class AuthorityRequiredError(BackendError):
    """Staff tried to send the reply of a ticket that requires authority (FR-06)."""

    code: ClassVar[ErrorCode] = ErrorCode.AUTHORITY_REQUIRED

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__(
            "Only a manager may send the reply of this ticket. Submit a reply proposal instead."
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConsoleTicket:
    """A ticket with its customer message, as staff and managers read it.

    Attributes:
        ticket_id: The identifier.
        status: The lifecycle state.
        handling_mode: Assisted or manual.
        is_authority_required: The sticky authority flag.
        created_at: When the customer asked.
        handling_started_at: The first staff view; absent before it.
        closed_at: When the reply was sent; absent before it.
        customer_id: The customer.
        order_id: The ticket's order; absent for an imported ticket without one.
        current_suggestion_id: The current suggestion; absent in manual mode.
        message: The customer's message. Confidential.
    """

    ticket_id: TicketId
    status: TicketStatus
    handling_mode: HandlingMode
    is_authority_required: bool
    created_at: datetime
    handling_started_at: datetime | None
    closed_at: datetime | None
    customer_id: CustomerId
    order_id: OrderId | None
    current_suggestion_id: SuggestionId | None
    message: str

    @property
    def message_excerpt(self) -> str:
        """Return at most the first 160 characters of the message."""
        return self.message[:MESSAGE_EXCERPT_LENGTH]


def compute_allowed_actions(
    ticket: ConsoleTicket, suggestion: Suggestion | None, role: SupportRole
) -> frozenset[TicketAction]:
    """Compute the actions that the caller may take now (contracts v1 design).

    Args:
        ticket: The ticket.
        suggestion: Its current suggestion, when it has one.
        role: The caller's role.

    Returns:
        The actions; empty on a `closed` ticket, and for staff on a ticket that is not `open`.
    """
    if not _may_act_on(ticket, role):
        return frozenset()
    is_pending = suggestion is not None and suggestion.has_pending_part
    actions: set[TicketAction] = set()
    if not is_pending and _may_send(ticket, role):
        actions.add(TicketAction.SEND_REPLY)
    if ticket.status is TicketStatus.OPEN:
        actions.update(_open_ticket_actions(ticket, suggestion, role, is_pending=is_pending))
    return frozenset(actions)


def check_reply_allowed(
    ticket: ConsoleTicket, suggestion: Suggestion | None, role: SupportRole
) -> None:
    """Run steps 4 to 6 of the check order of `sendReply`.

    Args:
        ticket: The ticket, locked by the transaction.
        suggestion: Its current suggestion, when it has one.
        role: The caller's role.

    Raises:
        InvalidTicketStateError: The ticket is `closed`.
        ForbiddenRoleError: Staff on a ticket that is not `open`.
        AuthorityRequiredError: Staff on a ticket that requires authority, also while a part
            is pending, because the flag is never cleared.
        SuggestionPendingError: A part of the current suggestion is pending.
    """
    if ticket.status is TicketStatus.CLOSED:
        raise InvalidTicketStateError(ticket.status.value)
    if role is SupportRole.STAFF and ticket.status is not TicketStatus.OPEN:
        raise ForbiddenRoleError
    if role is SupportRole.STAFF and ticket.is_authority_required:
        raise AuthorityRequiredError
    if suggestion is not None and suggestion.has_pending_part:
        raise SuggestionPendingError


def check_suggestion_is_current(ticket: ConsoleTicket, suggestion_id: SuggestionId | None) -> None:
    """Run step 7 of the check order: a `suggestion_id` of the body names the current one.

    Args:
        ticket: The ticket.
        suggestion_id: The `suggestion_id` of the body, when it has one.

    Raises:
        SuggestionSupersededError: It names another suggestion, or the ticket has none.
    """
    if suggestion_id is not None and suggestion_id != ticket.current_suggestion_id:
        raise SuggestionSupersededError


def _may_act_on(ticket: ConsoleTicket, role: SupportRole) -> bool:
    if ticket.status is TicketStatus.CLOSED:
        return False
    return role is SupportRole.MANAGER or ticket.status is TicketStatus.OPEN


def _may_send(ticket: ConsoleTicket, role: SupportRole) -> bool:
    return role is SupportRole.MANAGER or not ticket.is_authority_required


def _open_ticket_actions(
    ticket: ConsoleTicket, suggestion: Suggestion | None, role: SupportRole, *, is_pending: bool
) -> set[TicketAction]:
    actions: set[TicketAction] = set()
    if role is SupportRole.STAFF:
        actions.add(TicketAction.ESCALATE)
        if not is_pending:
            actions.add(TicketAction.SUBMIT_REPLY_PROPOSAL)
    if ticket.handling_mode is HandlingMode.MANUAL or suggestion is None:
        return actions
    if suggestion.known_intent is not None:
        actions.add(TicketAction.CORRECT_INTENT)
    if suggestion.can_retry:
        actions.add(TicketAction.RETRY_SUGGESTION)
    return actions
