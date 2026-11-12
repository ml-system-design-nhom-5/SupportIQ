"""In-memory fakes of the console ports of tickets, and a harness of the console use cases."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime

from supportiq_backend.accounts import AccountId, Authorizer, DisplayName
from supportiq_backend.idempotency import IdempotencyGuard
from supportiq_backend.suggestions import (
    SuggestionStarter,
    SuggestionStarterPorts,
    SuggestionTicketId,
    TicketForSuggestion,
)
from supportiq_backend.tickets import (
    ConsolePorts,
    ConsoleStores,
    ConsoleTicket,
    ConsoleTicketPosition,
    RecordedDecision,
    SentReply,
    TicketId,
    TicketStatus,
)
from tests.unit.audit.fakes import FakeAuditLog
from tests.unit.idempotency.fakes import FakeIdempotencyStore
from tests.unit.platform.fakes import (
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)
from tests.unit.pseudonymization.fakes import FakeCustomerRecords
from tests.unit.suggestions.builders import STAFF_ACCOUNT_ID
from tests.unit.suggestions.fakes import (
    FakeAiService,
    FakeRestorer,
    FakeSuggestionStore,
    FakeTicketLinks,
    RecordingSuggestionQueue,
)

RETENTION_MS = 86_400_000
STAFF_NAME = DisplayName("Staff One")


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


@dataclass(slots=True)
class ConsoleHarness:
    """The stores and ports of the console use cases."""

    tickets: FakeConsoleTicketStore
    replies: FakeReplyStore
    suggestions: FakeSuggestionStore
    links: FakeTicketLinks
    audit: FakeAuditLog
    events: RecordingEventRecorder
    queue: RecordingSuggestionQueue
    ai_service: FakeAiService
    transactions: FakeTransactionRunner[ConsoleStores]
    ports: ConsolePorts


def build_console_harness(
    *tickets: ConsoleTicket,
    ai_service: FakeAiService | None = None,
    restorer: FakeRestorer | None = None,
) -> ConsoleHarness:
    ticket_store = FakeConsoleTicketStore({ticket.ticket_id: ticket for ticket in tickets})
    suggestions = FakeSuggestionStore()
    links = FakeTicketLinks(
        tickets={
            SuggestionTicketId(ticket.ticket_id): TicketForSuggestion(
                ticket.current_suggestion_id, True, True, ticket.status.value
            )
            for ticket in tickets
        }
    )
    replies = FakeReplyStore()
    audit = FakeAuditLog()
    events = RecordingEventRecorder()
    queue = RecordingSuggestionQueue()
    clock = FakeClock()
    service = ai_service or FakeAiService()
    transactions = FakeTransactionRunner(
        ConsoleStores(
            tickets=ticket_store,
            replies=replies,
            suggestions=suggestions,
            links=links,
            records=FakeCustomerRecords(),
            staff=FakeStaffDirectory(),
            restorer=restorer or FakeRestorer(),
            idempotency=FakeIdempotencyStore(),
            audit=audit,
        )
    )
    ports = ConsolePorts(
        authorizer=Authorizer(events),
        guard=IdempotencyGuard(clock, RETENTION_MS),
        clock=clock,
        ids=SequentialIdGenerator(start=500),
        traces=FixedTraceContext(),
        events=events,
        steps=RecordingStepTracer(),
        starter=SuggestionStarter(
            SuggestionStarterPorts(
                clock=clock,
                ids=SequentialIdGenerator(start=900),
                traces=FixedTraceContext(),
                events=events,
                queue=queue,
            )
        ),
        ai_service=service,
    )
    return ConsoleHarness(
        ticket_store,
        replies,
        suggestions,
        links,
        audit,
        events,
        queue,
        service,
        transactions,
        ports,
    )
