"""A harness of the console use cases of tickets, on in-memory fakes of their ports."""

import json
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from supportiq_backend.accounts import (
    AccountId,
    Authorizer,
    CustomerPrincipal,
    InternalPrincipal,
    InternalRole,
    SupportPrincipal,
    SupportRole,
)
from supportiq_backend.idempotency import IdempotencyGuard, IdempotencyKey, StoredResponse
from supportiq_backend.suggestions import (
    Suggestion,
    SuggestionStarter,
    SuggestionStarterPorts,
    SuggestionTicketId,
    TicketForSuggestion,
)
from supportiq_backend.tickets import (
    ConsolePorts,
    ConsoleStores,
    ConsoleTicket,
    CreateEscalation,
    CreateReplyProposal,
    EscalationRecord,
    GetConsoleTicket,
    HandlingMode,
    ListConsoleTickets,
    ProposalRecord,
    RecordTicketView,
    ReplyRecord,
    SendReply,
    TicketId,
    TicketStatus,
)
from tests.unit.audit.fakes import FakeAuditLog
from tests.unit.idempotency.fakes import FakeIdempotencyStore
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)
from tests.unit.pseudonymization.fakes import CUSTOMER_ID, REFERENCES, FakeCustomerRecords
from tests.unit.suggestions.builders import STAFF_ACCOUNT_ID
from tests.unit.suggestions.fakes import (
    FakeAiService,
    FakeRestorer,
    FakeSuggestionStore,
    FakeTicketLinks,
    RecordingProgressNotifier,
    RecordingSuggestionQueue,
)
from tests.unit.tickets.fakes import (
    MANAGER_ACCOUNT_ID,
    FakeConsoleTicketStore,
    FakeEscalationStore,
    FakeReplyProposalStore,
    FakeReplyStore,
    FakeStaffDirectory,
    FakeTicketStateStore,
    TickingClock,
)

RETENTION_MS = 86_400_000
TICKET_ID = TicketId("TCK-1042")
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000123"))
# The callers after the role check of a console use case.
STAFF = SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.STAFF)
MANAGER = SupportPrincipal(MANAGER_ACCOUNT_ID, SupportRole.MANAGER)
# The callers as signed in, before any role check.
SIGNED_IN_STAFF = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.STAFF)
SIGNED_IN_MANAGER = InternalPrincipal(MANAGER_ACCOUNT_ID, InternalRole.MANAGER)
CUSTOMER = CustomerPrincipal(AccountId("00000000-0000-4000-8000-0000000000cc"), CUSTOMER_ID)
ADMIN = InternalPrincipal(AccountId("00000000-0000-4000-8000-0000000000ad"), InternalRole.ADMIN)


@dataclass(slots=True)
class ConsoleHarness:
    """The stores and ports of the console use cases."""

    tickets: FakeConsoleTicketStore
    replies: FakeReplyStore
    proposals: FakeReplyProposalStore
    escalations: FakeEscalationStore
    suggestions: FakeSuggestionStore
    links: FakeTicketLinks
    records: FakeCustomerRecords
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
    fakes = _FakeStores.of(tickets)
    events = RecordingEventRecorder()
    queue = RecordingSuggestionQueue()
    service = ai_service or FakeAiService()
    return ConsoleHarness(
        tickets=fakes.tickets,
        replies=fakes.replies,
        proposals=fakes.proposals,
        escalations=fakes.escalations,
        suggestions=fakes.suggestions,
        links=fakes.links,
        records=fakes.records,
        audit=fakes.audit,
        events=events,
        queue=queue,
        ai_service=service,
        transactions=FakeTransactionRunner(fakes.to_console_stores(restorer or FakeRestorer())),
        ports=_build_ports(events, queue, service),
    )


def build_console_ticket(
    ticket_id: TicketId = TICKET_ID,
    *,
    status: TicketStatus = TicketStatus.OPEN,
    handling_mode: HandlingMode = HandlingMode.ASSISTED,
    is_authority_required: bool = False,
    handling_started_at: datetime | None = None,
) -> ConsoleTicket:
    """Build a ticket of the one customer about its one order, without a current suggestion."""
    return ConsoleTicket(
        ticket_id=ticket_id,
        status=status,
        handling_mode=handling_mode,
        is_authority_required=is_authority_required,
        created_at=FAKE_CLOCK_START,
        handling_started_at=handling_started_at,
        closed_at=None,
        customer_id=CUSTOMER_ID,
        order_id=REFERENCES.order_id,
        current_suggestion_id=None,
        message="Where is my refund?",
    )


def with_suggestion(harness: ConsoleHarness, suggestion: Suggestion) -> ConsoleHarness:
    """Keep the suggestion and make it the current suggestion of its ticket."""
    ticket_id = TicketId(suggestion.ticket_id)
    ticket = replace(
        harness.tickets.tickets[ticket_id], current_suggestion_id=suggestion.suggestion_id
    )
    harness.tickets.tickets[ticket_id] = ticket
    harness.links.tickets[suggestion.ticket_id] = _link_of(ticket)
    harness.suggestions.data.add(suggestion)
    return harness


def with_ticking_clock(harness: ConsoleHarness) -> ConsoleHarness:
    """Give the use cases a clock that moves after each read, to prove one read per action."""
    harness.ports = replace(harness.ports, clock=TickingClock())
    return harness


def build_list(harness: ConsoleHarness) -> ListConsoleTickets:
    """Build `listConsoleTickets` on the harness."""
    return ListConsoleTickets(harness.transactions, harness.ports)


def build_get(harness: ConsoleHarness) -> GetConsoleTicket:
    """Build `getConsoleTicket` on the harness."""
    return GetConsoleTicket(harness.transactions, harness.ports)


def build_view(harness: ConsoleHarness) -> RecordTicketView:
    """Build `recordTicketView` on the harness."""
    return RecordTicketView(harness.transactions, harness.ports)


def build_send(harness: ConsoleHarness) -> SendReply:
    """Build `sendReply` on the harness, with a response that names the reply."""
    return SendReply(harness.transactions, harness.ports, _render_reply)


def build_propose(harness: ConsoleHarness) -> CreateReplyProposal:
    """Build `createReplyProposal` on the harness, with a response that names the proposal."""
    return CreateReplyProposal(harness.transactions, harness.ports, _render_proposal)


def build_escalate(harness: ConsoleHarness) -> CreateEscalation:
    """Build `createEscalation` on the harness, with a response that names the escalation."""
    return CreateEscalation(harness.transactions, harness.ports, _render_escalation)


@dataclass(frozen=True, slots=True)
class _FakeStores:
    """The fakes that the tests of the console inspect."""

    tickets: FakeConsoleTicketStore
    replies: FakeReplyStore
    proposals: FakeReplyProposalStore
    escalations: FakeEscalationStore
    suggestions: FakeSuggestionStore
    links: FakeTicketLinks
    records: FakeCustomerRecords
    audit: FakeAuditLog

    @classmethod
    def of(cls, tickets: tuple[ConsoleTicket, ...]) -> "_FakeStores":
        """Build empty stores that hold the tickets."""
        return cls(
            tickets=FakeConsoleTicketStore({ticket.ticket_id: ticket for ticket in tickets}),
            replies=FakeReplyStore(),
            proposals=FakeReplyProposalStore(),
            escalations=FakeEscalationStore(),
            suggestions=FakeSuggestionStore(),
            links=FakeTicketLinks(
                tickets={
                    SuggestionTicketId(ticket.ticket_id): _link_of(ticket) for ticket in tickets
                }
            ),
            records=FakeCustomerRecords(),
            audit=FakeAuditLog(),
        )

    def to_console_stores(self, restorer: FakeRestorer) -> ConsoleStores:
        """Return the stores of the use cases, with the fakes that nothing inspects."""
        return ConsoleStores(
            tickets=self.tickets,
            ticket_states=FakeTicketStateStore(self.tickets.tickets),
            replies=self.replies,
            proposals=self.proposals,
            escalations=self.escalations,
            suggestions=self.suggestions,
            links=self.links,
            records=self.records,
            staff=FakeStaffDirectory(),
            restorer=restorer,
            idempotency=FakeIdempotencyStore(),
            audit=self.audit,
        )


def _build_ports(
    events: RecordingEventRecorder, queue: RecordingSuggestionQueue, ai_service: FakeAiService
) -> ConsolePorts:
    clock = FakeClock()
    return ConsolePorts(
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
                progress=RecordingProgressNotifier(),
            )
        ),
        ai_service=ai_service,
    )


def _link_of(ticket: ConsoleTicket) -> TicketForSuggestion:
    return TicketForSuggestion(ticket.current_suggestion_id, True, True, ticket.status.value)


def _render_reply(record: ReplyRecord) -> StoredResponse:
    return StoredResponse(201, json.dumps({"reply_id": str(record.reply.reply_id)}))


def _render_proposal(record: ProposalRecord) -> StoredResponse:
    return StoredResponse(201, json.dumps({"proposal_id": str(record.proposal.proposal_id)}))


def _render_escalation(record: EscalationRecord) -> StoredResponse:
    return StoredResponse(201, json.dumps({"escalation_id": str(record.escalation.escalation_id)}))
