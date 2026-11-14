"""Rows of the report and export tests, inserted as the owner with explicit times (TEST-05).

Every figure of the report counts records by their times, so each row here takes the times
that a test needs and nothing else that matters to it. Tickets are imported tickets without an
order, so no commerce row is needed. Final suggestion parts are inserted as final, as the claim
loop leaves them. Every value is synthetic (TEST-18).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import insert, null, text, update
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import Executable

from supportiq_backend.suggestions.adapters.tables import SuggestionPartRow, SuggestionRow
from supportiq_backend.tickets.adapters.tables import (
    CustomerMessageRow,
    EscalationRow,
    ReplyRow,
    StaffDecisionRow,
    TicketRow,
)
from tests.integration.builders import DatabaseBuilder

START_AT = datetime(2026, 11, 2, tzinfo=UTC)
END_AT = datetime(2026, 11, 9, tzinfo=UTC)
START_TEXT = "2026-11-02T00:00:00Z"
END_TEXT = "2026-11-09T00:00:00Z"
PERIOD = {"start_at": START_TEXT, "end_at": END_TEXT}
BEFORE_START = START_AT - timedelta(days=1)
ONE_MICROSECOND = timedelta(microseconds=1)
CONSOLE_REPORTS = "/v1/console/reports"
PENDING = "pending"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_INSERT_MAP_ENTRY = """
    INSERT INTO pseudonym_map_entries
        (ticket_id, pseudonym, pseudonym_type, original_value, created_at)
    VALUES (:ticket_id, :pseudonym, 'ORDER_ID', :original_value, :created_at)
"""


@dataclass(frozen=True, slots=True)
class ReportTicketSpec:
    """A ticket to insert, with its customer message.

    Attributes:
        created_at: When it was created.
        handling_mode: `assisted` or `manual`.
        status: Its status.
        handling_started_at: Its first view, if any.
        closed_at: When its reply was sent, if it was.
        study_pair_id: Its study pair, if any.
        study_batch: Its study batch, if any.
        message: The customer message, as the customer wrote it.
    """

    created_at: datetime
    handling_mode: str = "assisted"
    status: str = "open"
    handling_started_at: datetime | None = None
    closed_at: datetime | None = None
    study_pair_id: str | None = None
    study_batch: str | None = None
    message: str = "Where is my parcel?"


@dataclass(frozen=True, slots=True)
class PartRowSpec:
    """One part of a suggestion, as stored.

    Attributes:
        status: The status.
        completed_at: When it left `pending`; None exactly for a pending part.
        reason_codes: The AI reason codes.
        llm_cost_micro_usd: The LLM cost, if the LLM answered.
        result: The ai-service response, if the part has one.
    """

    status: str = PENDING
    completed_at: datetime | None = None
    reason_codes: tuple[str, ...] = ()
    llm_cost_micro_usd: int | None = None
    result: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SuggestionRowSpec:
    """A suggestion to insert with its two parts.

    Attributes:
        created_at: When it was created.
        analysis: The analysis part.
        draft: The draft part.
        request: The stored request; None before pseudonymization succeeded.
        is_retry: Whether staff asked for it as a retry, rather than the ticket's creation.
        intent_override: The intent that staff chose, for a suggestion of an intent override.
    """

    created_at: datetime
    analysis: PartRowSpec = field(default_factory=PartRowSpec)
    draft: PartRowSpec = field(default_factory=PartRowSpec)
    request: dict[str, object] | None = None
    is_retry: bool = False
    intent_override: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionRowSpec:
    """A staff decision to insert.

    Attributes:
        decision_type: Approve, edit, reject, or escalate.
        decided_at: When it was recorded.
        staff_reason_codes: Its staff reason codes.
        suggestion_id: The suggestion it was about, if any.
        change_ratio: The change ratio, if any.
        final_intent: The final intent, if any.
    """

    decision_type: str
    decided_at: datetime
    staff_reason_codes: tuple[str, ...] = ()
    suggestion_id: UUID | None = None
    change_ratio: float | None = None
    final_intent: str | None = None


@dataclass(frozen=True, slots=True)
class EscalationRowSpec:
    """An escalated ticket to insert.

    Attributes:
        escalated_at: When it was escalated.
        staff_reason_codes: The staff reason codes of the escalation.
    """

    escalated_at: datetime
    staff_reason_codes: tuple[str, ...]


def completed(status: str, completed_at: datetime, *reason_codes: str) -> PartRowSpec:
    """Describe a part that left `pending` with a status and reason codes, without a result."""
    return PartRowSpec(status=status, completed_at=completed_at, reason_codes=reason_codes)


def closed_after(mode: str, closed_at: datetime, handling: timedelta) -> ReportTicketSpec:
    """Describe a ticket closed some time after its first view."""
    return ReportTicketSpec(
        created_at=closed_at - handling,
        handling_mode=mode,
        status="closed",
        handling_started_at=closed_at - handling,
        closed_at=closed_at,
    )


class ReportRows:
    """Insert the rows of the report and export tests, each call in its own transaction."""

    def __init__(self, engine: AsyncEngine, builder: DatabaseBuilder, account_id: UUID) -> None:
        """Keep the owner engine, the builder of IDs, and the staff account of every action.

        Args:
            engine: An engine that connects as the owner.
            builder: Gives every row a deterministic ID.
            account_id: The account that decides, escalates, sends, and asks for retries.
        """
        self._engine = engine
        self._builder = builder
        self._account_id = account_id

    async def ticket(self, spec: ReportTicketSpec) -> str:
        """Insert an imported ticket of a new customer with its message; return its ID."""
        customer_id = await self._builder.customer()
        async with self._engine.begin() as connection:
            ticket_id = await connection.scalar(
                insert(TicketRow)
                .values(
                    customer_id=customer_id,
                    order_id=None,
                    status=spec.status,
                    handling_mode=spec.handling_mode,
                    source="import",
                    created_at=spec.created_at,
                    handling_started_at=spec.handling_started_at,
                    closed_at=spec.closed_at,
                    study_pair_id=spec.study_pair_id,
                    study_batch=spec.study_batch,
                )
                .returning(TicketRow.ticket_id)
            )
            await connection.execute(
                insert(CustomerMessageRow).values(
                    message_id=self._builder.next_uuid(),
                    ticket_id=ticket_id,
                    body=spec.message,
                    created_at=spec.created_at,
                )
            )
        return str(ticket_id)

    async def tickets(self, *specs: ReportTicketSpec) -> tuple[str, ...]:
        """Insert several tickets, in order; return their IDs."""
        return tuple([await self.ticket(spec) for spec in specs])

    async def ticket_with_first_draft(self, created_at: datetime, latency: timedelta) -> str:
        """Insert a ticket whose first suggestion has a draft ready some time after creation."""
        ticket_id = await self.ticket(ReportTicketSpec(created_at=created_at))
        draft = completed("draft_ready", created_at + latency)
        await self.suggestion(ticket_id, SuggestionRowSpec(created_at=created_at, draft=draft))
        return ticket_id

    async def suggestions(self, ticket_id: str, *specs: SuggestionRowSpec) -> None:
        """Insert several suggestions of one ticket, in order; the last one is current."""
        for spec in specs:
            await self.suggestion(ticket_id, spec)

    async def decisions(self, ticket_id: str, *specs: DecisionRowSpec) -> None:
        """Insert several staff decisions about one ticket."""
        for spec in specs:
            await self.decision(ticket_id, spec)

    async def escalated_tickets(self, *specs: EscalationRowSpec) -> None:
        """Insert one escalated ticket with its escalation per spec."""
        for spec in specs:
            ticket_id = await self.ticket(
                ReportTicketSpec(created_at=spec.escalated_at, status="escalated")
            )
            await self.escalation(ticket_id, spec.escalated_at, *spec.staff_reason_codes)

    async def suggestion(self, ticket_id: str, spec: SuggestionRowSpec) -> UUID:
        """Insert a suggestion with its parts and make it the ticket's current one."""
        suggestion_id = self._builder.next_uuid()
        await self._insert(
            insert(SuggestionRow).values(
                suggestion_id=suggestion_id,
                ticket_id=ticket_id,
                trigger=_trigger_of(spec),
                intent_override=spec.intent_override,
                requested_by_account_id=(
                    None if _trigger_of(spec) == "ticket_created" else self._account_id
                ),
                created_at=spec.created_at,
                trace_id=TRACE_ID,
                request=null() if spec.request is None else spec.request,
            ),
            _insert_part(suggestion_id, "analysis", spec.analysis),
            _insert_part(suggestion_id, "draft", spec.draft),
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id)
            .values(current_suggestion_id=suggestion_id),
        )
        return suggestion_id

    async def decision(self, ticket_id: str, spec: DecisionRowSpec) -> None:
        """Insert a staff decision about a ticket."""
        await self._insert(
            insert(StaffDecisionRow).values(
                decision_id=self._builder.next_uuid(),
                ticket_id=ticket_id,
                suggestion_id=spec.suggestion_id,
                decision_type=spec.decision_type,
                staff_reason_codes=list(spec.staff_reason_codes),
                change_ratio=spec.change_ratio,
                final_intent=spec.final_intent,
                decided_by_account_id=self._account_id,
                decided_at=spec.decided_at,
            )
        )

    async def escalation(
        self,
        ticket_id: str,
        escalated_at: datetime,
        *staff_reason_codes: str,
        note: str | None = None,
    ) -> None:
        """Insert the escalation of a ticket."""
        await self._insert(
            insert(EscalationRow).values(
                escalation_id=self._builder.next_uuid(),
                ticket_id=ticket_id,
                staff_reason_codes=list(staff_reason_codes),
                escalated_by_account_id=self._account_id,
                escalated_at=escalated_at,
                note=note,
            )
        )

    async def reply(
        self, ticket_id: str, suggestion_id: UUID, sent_at: datetime, body: str, note: str
    ) -> None:
        """Insert the reply of a ticket, sent from its AI draft, with a note."""
        await self._insert(
            insert(ReplyRow).values(
                reply_id=self._builder.next_uuid(),
                ticket_id=ticket_id,
                basis="ai_draft",
                suggestion_id=suggestion_id,
                acknowledged_warning_ids=[],
                staff_reason_codes=[],
                sent_by_account_id=self._account_id,
                sent_at=sent_at,
                body=body,
                note=note,
            )
        )

    async def map_entry(self, ticket_id: str, pseudonym: str, original_value: str) -> None:
        """Insert one entry of a ticket's pseudonym map."""
        async with self._engine.begin() as connection:
            await connection.execute(
                text(_INSERT_MAP_ENTRY),
                {
                    "ticket_id": ticket_id,
                    "pseudonym": pseudonym,
                    "original_value": original_value,
                    "created_at": START_AT,
                },
            )

    async def _insert(self, *statements: Executable) -> None:
        async with self._engine.begin() as connection:
            for statement in statements:
                await connection.execute(statement)


def _trigger_of(spec: SuggestionRowSpec) -> str:
    if spec.intent_override is not None:
        return "intent_override"
    return "retry" if spec.is_retry else "ticket_created"


def _insert_part(suggestion_id: UUID, part: str, spec: PartRowSpec) -> Executable:
    return insert(SuggestionPartRow).values(
        suggestion_id=suggestion_id,
        part=part,
        status=spec.status,
        reason_codes=list(spec.reason_codes),
        llm_cost_micro_usd=spec.llm_cost_micro_usd,
        completed_at=spec.completed_at,
        result=null() if spec.result is None else spec.result,
    )
