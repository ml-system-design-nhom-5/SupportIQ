"""In-memory fakes of the store ports of tickets (ARCH-27)."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime

from supportiq_backend.accounts import AccountId, CustomerId, DisplayName
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform import BackendError
from supportiq_backend.tickets import (
    ConsoleTicket,
    ConsoleTicketPosition,
    RecordedDecision,
    SentReply,
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketPosition,
    TicketStatus,
)
from tests.unit.suggestions.builders import STAFF_ACCOUNT_ID

FIRST_TICKET_ID = TicketId("TCK-1001")
STAFF_NAME = DisplayName("Staff One")


@dataclass(slots=True)
class FakeTicketStore:
    """Keep inserted records, and serve given tickets in the contract's order."""

    tickets: dict[CustomerId, tuple[ShopTicket, ...]] = field(
        default_factory=dict[CustomerId, tuple[ShopTicket, ...]]
    )
    inserted: list[ShopTicketRecord] = field(default_factory=list[ShopTicketRecord])
    insert_failure: BackendError | None = None
    load_failure: BackendError | None = None

    async def insert_shop_ticket(self, record: ShopTicketRecord) -> TicketId:
        """Keep the record and return the same ID each time, or raise the chosen failure."""
        if self.insert_failure is not None:
            raise self.insert_failure
        self.inserted.append(record)
        return FIRST_TICKET_ID

    async def load_shop_ticket(
        self, customer_id: CustomerId, ticket_id: TicketId
    ) -> ShopTicket | None:
        """Return the ticket of the customer, if any."""
        if self.load_failure is not None:
            raise self.load_failure
        tickets = self.tickets.get(customer_id, ())
        return next((ticket for ticket in tickets if ticket.ticket_id == ticket_id), None)

    async def load_shop_tickets(
        self,
        customer_id: CustomerId,
        *,
        order_id: OrderId | None,
        after: TicketPosition | None,
        limit: int,
    ) -> tuple[ShopTicket, ...]:
        """Return the tickets after the position, about the order when one is given."""
        if self.load_failure is not None:
            raise self.load_failure
        tickets = tuple(
            ticket
            for ticket in self.tickets.get(customer_id, ())
            if order_id is None or ticket.order_id == order_id
        )
        position = 0
        if after is not None:
            position = 1 + [ticket.ticket_id for ticket in tickets].index(after.ticket_id)
        return tickets[position : position + limit]


@dataclass(slots=True)
class FakeConsoleTicketStore:
    """Keep console tickets by ID."""

    tickets: dict[TicketId, ConsoleTicket] = field(default_factory=dict[TicketId, ConsoleTicket])

    async def lock_console_ticket(self, ticket_id: TicketId) -> ConsoleTicket | None:
        """Return the ticket."""
        return self.tickets.get(ticket_id)

    async def load_console_ticket(self, ticket_id: TicketId) -> ConsoleTicket | None:
        """Return the ticket."""
        return self.tickets.get(ticket_id)

    async def load_console_tickets(
        self, status: TicketStatus, *, after: ConsoleTicketPosition | None, limit: int
    ) -> tuple[ConsoleTicket, ...]:
        """Return the tickets of a status in insertion order."""
        del after
        return tuple(ticket for ticket in self.tickets.values() if ticket.status is status)[:limit]

    async def start_handling(self, ticket_id: TicketId, started_at: datetime) -> None:
        """Start the handling clock."""
        self.tickets[ticket_id] = replace(self.tickets[ticket_id], handling_started_at=started_at)

    async def close_ticket(self, ticket_id: TicketId, closed_at: datetime) -> None:
        """Close the ticket."""
        self.tickets[ticket_id] = replace(
            self.tickets[ticket_id], status=TicketStatus.CLOSED, closed_at=closed_at
        )


@dataclass(slots=True)
class FakeReplyStore:
    """Keep replies and decisions."""

    replies: dict[TicketId, SentReply] = field(default_factory=dict[TicketId, SentReply])
    decisions: list[RecordedDecision] = field(default_factory=list[RecordedDecision])

    async def insert_reply(self, reply: SentReply) -> None:
        """Keep the one reply of a ticket."""
        assert reply.ticket_id not in self.replies
        self.replies[reply.ticket_id] = reply

    async def load_reply(self, ticket_id: TicketId) -> SentReply | None:
        """Return the reply of a ticket."""
        return self.replies.get(ticket_id)

    async def insert_decision(self, decision: RecordedDecision) -> None:
        """Keep the decision."""
        self.decisions.append(decision)


@dataclass(slots=True)
class FakeStaffDirectory:
    """Name the one staff account of the tests."""

    async def load_display_names(
        self, account_ids: frozenset[AccountId]
    ) -> Mapping[AccountId, DisplayName]:
        """Return the name of the known account."""
        return {STAFF_ACCOUNT_ID: STAFF_NAME} if STAFF_ACCOUNT_ID in account_ids else {}
