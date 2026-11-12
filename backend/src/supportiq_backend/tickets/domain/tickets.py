"""Tickets as the shop sees them (ADR-0013).

A ticket ID is Internal. The order ID and the customer's message are Confidential, so the
classes that hold them have no generated `repr`, and neither reaches a log, a trace, or an
error (LOG-29).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform import RequestContractError, is_storable_text

TicketId = NewType("TicketId", str)

_MESSAGE_LOCATION = "body.message"


class TicketStatus(StrEnum):
    """The status of a ticket, as `tickets.status` holds it (contracts v1, Ticket lifecycle)."""

    OPEN = "open"
    AWAITING_APPROVAL = "awaiting_approval"
    ESCALATED = "escalated"
    CLOSED = "closed"


class HandlingMode(StrEnum):
    """Whether a ticket is handled with AI suggestions or without them."""

    ASSISTED = "assisted"
    MANUAL = "manual"


class TicketSource(StrEnum):
    """Where a ticket comes from. The shop shows only tickets that it created."""

    SHOP = "shop"
    IMPORT = "import"


@dataclass(frozen=True, slots=True, repr=False)
class NewShopTicket:
    """What a customer sends to create a ticket.

    Attributes:
        order_id: The order that the message is about, as the request sent it.
        message: The message, exactly as written.
    """

    order_id: OrderId
    message: str


@dataclass(frozen=True, slots=True, repr=False)
class ShopTicketRecord:
    """Everything that the store writes for a new shop ticket.

    Attributes:
        customer_id: The customer who wrote.
        ticket: The order and the message.
        message_id: The identifier of the customer message.
        handling_mode: The handling mode of the ticket.
        created_at: When the customer sent the message.
    """

    customer_id: CustomerId
    ticket: NewShopTicket
    message_id: UUID
    handling_mode: HandlingMode
    created_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class ShopReply:
    """The reply that staff sent, as the customer reads it. The body is Confidential.

    Attributes:
        body: The text, exactly as staff sent it.
        sent_at: When it was sent.
    """

    body: str
    sent_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class ShopTicket:
    """A customer's ticket, as the shop shows it. It holds no AI output (ADR-0013).

    Attributes:
        ticket_id: The identifier.
        order_id: The order that the ticket is about.
        message: The customer's message, exactly as written.
        created_at: When the customer sent the message.
        reply: The reply, once staff sent it.
    """

    ticket_id: TicketId
    order_id: OrderId
    message: str
    created_at: datetime
    reply: ShopReply | None = None


@dataclass(frozen=True, slots=True)
class TicketPosition:
    """The place of a ticket in the list order, from Internal values only.

    Attributes:
        created_at: When the last ticket of a page was created.
        ticket_id: Its identifier.
    """

    created_at: datetime
    ticket_id: TicketId


@dataclass(frozen=True, slots=True, repr=False)
class TicketPage:
    """One page of a customer's tickets.

    Attributes:
        items: The tickets of the page.
        next_position: The last ticket of the page when more follow.
    """

    items: tuple[ShopTicket, ...]
    next_position: TicketPosition | None


def build_new_shop_ticket(order_id: str, message: str) -> NewShopTicket:
    """Check what a customer sent, without changing it.

    An `order_id` that cannot be stored names no order, so the use case answers it like any
    unknown order. A message that cannot be stored would be lost, so it is an invalid request.

    Args:
        order_id: The order, as the request sent it.
        message: The message, as the request sent it.

    Returns:
        The new ticket.

    Raises:
        RequestContractError: PostgreSQL cannot store the message.
    """
    if not is_storable_text(message):
        raise RequestContractError((_MESSAGE_LOCATION,))
    return NewShopTicket(OrderId(order_id), message)
