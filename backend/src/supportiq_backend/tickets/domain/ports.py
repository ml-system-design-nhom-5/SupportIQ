"""The port of the tickets tables (ARCH-13)."""

from datetime import datetime
from typing import Protocol

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import OrderId
from supportiq_backend.tickets.domain.console import ConsoleTicket
from supportiq_backend.tickets.domain.replies import RecordedDecision, SentReply
from supportiq_backend.tickets.domain.tickets import (
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketPosition,
    TicketStatus,
)
from supportiq_backend.tickets.domain.workspace import ConsoleTicketPosition


class TicketStore(Protocol):
    """Writes shop tickets and reads them back, always for one customer (SEC-17)."""

    async def insert_shop_ticket(self, record: ShopTicketRecord) -> TicketId:
        """Insert an `open` ticket from the shop and its customer message.

        Args:
            record: What the ticket holds.

        Returns:
            The identifier that the database gave the ticket.
        """
        ...

    async def load_shop_ticket(
        self, customer_id: CustomerId, ticket_id: TicketId
    ) -> ShopTicket | None:
        """Load one ticket that the customer created through the shop.

        Args:
            customer_id: The customer.
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown, imported, or another customer's.
        """
        ...

    async def load_shop_tickets(
        self,
        customer_id: CustomerId,
        *,
        order_id: OrderId | None,
        after: TicketPosition | None,
        limit: int,
    ) -> tuple[ShopTicket, ...]:
        """Load the customer's shop tickets, newest first, then by ticket ID by code point.

        Args:
            customer_id: The customer.
            order_id: Only the tickets about this order, or None for every ticket.
            after: The last ticket of the previous page, or None for the first page.
            limit: The maximum number of tickets.

        Returns:
            The tickets.
        """
        ...


class ConsoleTicketStore(Protocol):
    """Read and change tickets for the console; every action locks the ticket row first."""

    async def lock_console_ticket(self, ticket_id: TicketId) -> ConsoleTicket | None:
        """Lock a ticket row with `SELECT ... FOR UPDATE` and load it with its message.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.
        """
        ...

    async def load_console_ticket(self, ticket_id: TicketId) -> ConsoleTicket | None:
        """Load a ticket with its message, without a lock.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.
        """
        ...

    async def load_console_tickets(
        self, status: TicketStatus, *, after: ConsoleTicketPosition | None, limit: int
    ) -> tuple[ConsoleTicket, ...]:
        """Load the tickets in one status, in the order of their queue.

        `open`, `awaiting_approval`, and `escalated` are ordered by `created_at`, oldest
        first; `closed` by `closed_at`, newest first; then by ticket ID by code point.

        Args:
            status: The queue.
            after: The last ticket of the previous page, or None for the first page.
            limit: The maximum number of tickets.

        Returns:
            The tickets.
        """
        ...

    async def start_handling(self, ticket_id: TicketId, started_at: datetime) -> None:
        """Set `handling_started_at`, which starts the handling clock (NFR-11).

        Args:
            ticket_id: The ticket, locked, whose clock has not started.
            started_at: The time of the first view.
        """
        ...

    async def close_ticket(self, ticket_id: TicketId, closed_at: datetime) -> None:
        """Set the ticket `closed`, when its reply is sent.

        Args:
            ticket_id: The ticket, locked.
            closed_at: When the reply was sent.
        """
        ...


class ReplyStore(Protocol):
    """Insert replies and staff decisions once, and read replies back (ERR-16)."""

    async def insert_reply(self, reply: SentReply) -> None:
        """Insert the one reply of a ticket; a second one is impossible.

        Args:
            reply: The reply.
        """
        ...

    async def load_reply(self, ticket_id: TicketId) -> SentReply | None:
        """Load the reply of a ticket.

        Args:
            ticket_id: The ticket.

        Returns:
            The reply, or None before it is sent.
        """
        ...

    async def insert_decision(self, decision: RecordedDecision) -> None:
        """Insert a staff decision; it holds no text (ADR-0006).

        Args:
            decision: The decision.
        """
        ...
