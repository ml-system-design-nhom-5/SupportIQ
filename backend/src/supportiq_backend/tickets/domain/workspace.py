"""The ticket workspace and the ticket summaries of the console (backend contract 1.2.0)."""

from dataclasses import dataclass
from datetime import datetime

from supportiq_backend.commerce import AddressedOrder, Order
from supportiq_backend.suggestions import Suggestion
from supportiq_backend.tickets.domain.console import ConsoleTicket, TicketAction
from supportiq_backend.tickets.domain.replies import SentReply
from supportiq_backend.tickets.domain.tickets import TicketId, TicketStatus


@dataclass(frozen=True, slots=True, repr=False)
class RestoredSuggestion:
    """A suggestion with the pseudonyms of its AI text restored, for staff only (ADR-0010).

    Attributes:
        suggestion: The suggestion as stored, with placeholders.
        segment_texts: The restored text of each draft segment, in order; empty without a
            ready draft.
        draft_text: The canonical text of the ready draft, built from the restored segments.
        staff_note: The restored staff note, when the draft outcome has one.
    """

    suggestion: Suggestion
    segment_texts: tuple[str, ...]
    draft_text: str | None
    staff_note: str | None


@dataclass(frozen=True, slots=True, repr=False)
class ReplyRecord:
    """A sent reply with the display name of its sender.

    Attributes:
        reply: The reply.
        sent_by_display_name: The name of the account that sent it. Confidential.
    """

    reply: SentReply
    sent_by_display_name: str


# The workspace lists at most this many other orders of the customer (`backend` contract
# 1.2.0, `TicketWorkspace.other_orders`, `maxItems`).
OTHER_ORDERS_LIMIT = 20


@dataclass(frozen=True, slots=True, repr=False)
class TicketWorkspace:
    """Everything that staff and managers see of one ticket.

    Attributes:
        ticket: The ticket and its message.
        customer_display_name: The customer's name. Confidential.
        order: The ticket's order with its address; absent without one.
        other_orders: The customer's other orders, newest first, at most
            `OTHER_ORDERS_LIMIT`. Never sent to ai-service.
        suggestion: The current suggestion, restored; absent in manual mode.
        reply: The sent reply, when the ticket is closed.
        allowed_actions: What the caller may do now.
    """

    ticket: ConsoleTicket
    customer_display_name: str
    order: AddressedOrder | None
    other_orders: tuple[Order, ...]
    suggestion: RestoredSuggestion | None
    reply: ReplyRecord | None
    allowed_actions: frozenset[TicketAction]


@dataclass(frozen=True, slots=True, repr=False)
class TicketSummary:
    """One ticket of a console queue.

    Attributes:
        ticket: The ticket and its message.
        customer_display_name: The customer's name. Confidential.
        suggestion: The current suggestion; absent in manual mode.
    """

    ticket: ConsoleTicket
    customer_display_name: str
    suggestion: Suggestion | None


@dataclass(frozen=True, slots=True)
class ConsoleTicketPosition:
    """The place of a ticket in the order of its queue, from Internal values only.

    Attributes:
        status: The queue; a cursor of one queue is refused by another.
        moment: `created_at`, or `closed_at` in the `closed` queue.
        ticket_id: The ticket.
    """

    status: TicketStatus
    moment: datetime
    ticket_id: TicketId


@dataclass(frozen=True, slots=True, repr=False)
class TicketSummaryPage:
    """One page of a console queue.

    Attributes:
        items: The summaries of the page.
        next_position: The last ticket of the page when more follow.
    """

    items: tuple[TicketSummary, ...]
    next_position: ConsoleTicketPosition | None
