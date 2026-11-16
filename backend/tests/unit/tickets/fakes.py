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
    Escalation,
    ManagerQueue,
    RecordedDecision,
    ReplyProposal,
    SentReply,
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketPosition,
    TicketStatus,
)
from tests.unit.platform.fakes import FakeClock
from tests.unit.suggestions.builders import STAFF_ACCOUNT_ID

FIRST_TICKET_ID = TicketId("TCK-1001")
STAFF_NAME = DisplayName("Staff One")
MANAGER_ACCOUNT_ID = AccountId("00000000-0000-4000-8000-0000000000bb")
MANAGER_NAME = DisplayName("Manager One")
_NAME_BY_ACCOUNT = {STAFF_ACCOUNT_ID: STAFF_NAME, MANAGER_ACCOUNT_ID: MANAGER_NAME}


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


@dataclass(slots=True)
class FakeTicketStateStore:
    """Change the tickets of a `FakeConsoleTicketStore`, whose mapping it shares."""

    tickets: dict[TicketId, ConsoleTicket]

    async def start_handling(self, ticket_id: TicketId, started_at: datetime) -> None:
        """Start the handling clock."""
        self.tickets[ticket_id] = replace(self.tickets[ticket_id], handling_started_at=started_at)

    async def move_to_manager_queue(self, ticket_id: TicketId, queue: ManagerQueue) -> None:
        """Move the ticket to the queue."""
        self.tickets[ticket_id] = replace(self.tickets[ticket_id], status=queue)

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
class FakeReplyProposalStore:
    """Keep the proposal of each ticket, or fail with a given error."""

    proposals: dict[TicketId, ReplyProposal] = field(default_factory=dict[TicketId, ReplyProposal])
    failure: BackendError | None = None

    async def insert_proposal(self, proposal: ReplyProposal) -> None:
        """Keep the one proposal of a ticket."""
        self._fail_when_chosen()
        assert proposal.ticket_id not in self.proposals
        self.proposals[proposal.ticket_id] = proposal

    async def load_proposal(self, ticket_id: TicketId) -> ReplyProposal | None:
        """Return the proposal of a ticket."""
        self._fail_when_chosen()
        return self.proposals.get(ticket_id)

    def _fail_when_chosen(self) -> None:
        if self.failure is not None:
            raise self.failure


@dataclass(slots=True)
class FakeEscalationStore:
    """Keep the escalation of each ticket, or fail with a given error."""

    escalations: dict[TicketId, Escalation] = field(default_factory=dict[TicketId, Escalation])
    failure: BackendError | None = None

    async def insert_escalation(self, escalation: Escalation) -> None:
        """Keep the one escalation of a ticket."""
        self._fail_when_chosen()
        assert escalation.ticket_id not in self.escalations
        self.escalations[escalation.ticket_id] = escalation

    async def load_escalation(self, ticket_id: TicketId) -> Escalation | None:
        """Return the escalation of a ticket."""
        self._fail_when_chosen()
        return self.escalations.get(ticket_id)

    def _fail_when_chosen(self) -> None:
        if self.failure is not None:
            raise self.failure


@dataclass(slots=True)
class FakeStaffDirectory:
    """Name the staff account and the manager account of the tests."""

    async def load_display_names(
        self, account_ids: frozenset[AccountId]
    ) -> Mapping[AccountId, DisplayName]:
        """Return the names of the known accounts among those asked for."""
        return {
            account_id: name
            for account_id, name in _NAME_BY_ACCOUNT.items()
            if account_id in account_ids
        }


class TickingClock(FakeClock):
    """A fake clock that moves one millisecond forward after each read, so no two reads agree.

    A use case that reads it once gives every record of its action the same time.
    """

    def now(self) -> datetime:
        """Return the current fake time, then move it forward."""
        moment = super().now()
        self.advance(1)
        return moment
