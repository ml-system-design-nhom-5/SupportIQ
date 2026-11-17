"""Rows of the report and export tests, inserted through `DatabaseBuilder` with explicit times.

Every figure of the report counts records by their times, so each row here takes the times
that a test needs and nothing else that matters to it. Every ticket is imported and has no
order, so no commerce row is needed. Final suggestion parts are inserted as final, as the claim
loop leaves them. One staff account decides, escalates, sends, and asks for new suggestions.
Every value is synthetic (TEST-18).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from http import HTTPStatus
from uuid import UUID

from sqlalchemy import insert, text

from supportiq_backend.reports import build_report_period
from supportiq_backend.tickets.adapters.tables import EscalationRow, ReplyRow, StaffDecisionRow
from tests.integration.application import RunningBackend
from tests.integration.builders import (
    DatabaseBuilder,
    SuggestionPartSpec,
    SuggestionSpec,
    TicketSpec,
)

START_AT = datetime(2026, 11, 2, tzinfo=UTC)
END_AT = datetime(2026, 11, 9, tzinfo=UTC)
START_TEXT = "2026-11-02T00:00:00Z"
END_TEXT = "2026-11-09T00:00:00Z"
PERIOD = {"start_at": START_TEXT, "end_at": END_TEXT}
REPORT_PERIOD = build_report_period(START_AT, END_AT)
BEFORE_START = START_AT - timedelta(days=1)
ONE_MICROSECOND = timedelta(microseconds=1)
SECOND = timedelta(seconds=1)
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
CONSOLE_REPORTS = "/v1/console/reports"
_INSERT_MAP_ENTRY = """
    INSERT INTO pseudonym_map_entries
        (ticket_id, pseudonym, pseudonym_type, original_value, created_at)
    VALUES (:ticket_id, :pseudonym, 'ORDER_ID', :original_value, :created_at)
"""

# Every ticket of these tests is imported, so it needs no order: only a shop ticket must have
# one (the check `tickets_shop_tickets_have_an_order`).
imported_ticket = partial(TicketSpec, source="import")


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
        is_proposal_changed: Whether the manager changed the reply proposal, for a reply sent
            from one.
    """

    decision_type: str
    decided_at: datetime
    staff_reason_codes: tuple[str, ...] = ()
    suggestion_id: UUID | None = None
    change_ratio: float | None = None
    final_intent: str | None = None
    is_proposal_changed: bool | None = None


@dataclass(frozen=True, slots=True)
class EscalationRowSpec:
    """An escalated ticket to insert.

    Attributes:
        escalated_at: When it was escalated.
        staff_reason_codes: The staff reason codes of the escalation.
    """

    escalated_at: datetime
    staff_reason_codes: tuple[str, ...]


def completed(status: str, completed_at: datetime, *reason_codes: str) -> SuggestionPartSpec:
    """Describe a part that left `pending` with a status and reason codes, without a result."""
    return SuggestionPartSpec(status=status, completed_at=completed_at, reason_codes=reason_codes)


def closed_after(mode: str, closed_at: datetime, handling: timedelta) -> TicketSpec:
    """Describe a ticket closed some time after its first view."""
    return imported_ticket(
        created_at=closed_at - handling,
        handling_mode=mode,
        status="closed",
        handling_started_at=closed_at - handling,
        closed_at=closed_at,
    )


async def load_report(backend: RunningBackend, headers: dict[str, str]) -> dict[str, object]:
    """Ask for the report of `PERIOD`, which must answer 200, and return its body."""
    response = await backend.client.get(CONSOLE_REPORTS, params=PERIOD, headers=headers)
    assert response.status_code == HTTPStatus.OK
    return response.json()


class ReportRows:
    """Insert the rows of the report and export tests, each call in its own transaction."""

    def __init__(self, builder: DatabaseBuilder, staff_account_id: UUID) -> None:
        """Keep the builder and the staff account of every action.

        Args:
            builder: Inserts every row, with deterministic IDs.
            staff_account_id: The account that decides, escalates, sends, and asks for new
                suggestions.
        """
        self._builder = builder
        self._staff_account_id = staff_account_id

    @property
    def staff_account_id(self) -> UUID:
        """Return the staff account, which asks for every suggestion that staff ask for."""
        return self._staff_account_id

    async def ticket(self, spec: TicketSpec) -> str:
        """Insert a ticket of a new customer, without an order; return its ID."""
        customer_id = await self._builder.customer()
        return await self._builder.ticket(customer_id, None, spec)

    async def tickets(self, *specs: TicketSpec) -> tuple[str, ...]:
        """Insert several tickets, in order; return their IDs."""
        return tuple([await self.ticket(spec) for spec in specs])

    async def ticket_with_first_suggestion(
        self, created_at: datetime, analysis: SuggestionPartSpec, draft: SuggestionPartSpec
    ) -> str:
        """Insert a ticket and its first suggestion, created at the same time; return its ID."""
        ticket_id = await self.ticket(imported_ticket(created_at=created_at))
        spec = SuggestionSpec(created_at=created_at, analysis=analysis, draft=draft)
        await self.suggestion(ticket_id, spec)
        return ticket_id

    async def ticket_with_first_draft(self, created_at: datetime, latency: timedelta) -> str:
        """Insert a ticket whose first draft is ready some time after its creation.

        The analysis part is ready halfway, so it is completed before the draft part.
        """
        return await self.ticket_with_first_suggestion(
            created_at,
            completed("ready", created_at + latency / 2),
            completed("draft_ready", created_at + latency),
        )

    async def suggestion(self, ticket_id: str, spec: SuggestionSpec) -> UUID:
        """Insert a suggestion with its parts and make it the ticket's current one."""
        return await self._builder.suggestion(ticket_id, spec)

    async def suggestions(self, ticket_id: str, *specs: SuggestionSpec) -> None:
        """Insert several suggestions of one ticket, in order; the last one is current."""
        for spec in specs:
            await self.suggestion(ticket_id, spec)

    async def decision(self, ticket_id: str, spec: DecisionRowSpec) -> None:
        """Insert a staff decision about a ticket."""
        await self._builder.execute(
            insert(StaffDecisionRow).values(
                decision_id=self._builder.next_uuid(),
                ticket_id=ticket_id,
                suggestion_id=spec.suggestion_id,
                decision_type=spec.decision_type,
                staff_reason_codes=list(spec.staff_reason_codes),
                change_ratio=spec.change_ratio,
                final_intent=spec.final_intent,
                is_proposal_changed=spec.is_proposal_changed,
                decided_by_account_id=self._staff_account_id,
                decided_at=spec.decided_at,
            )
        )

    async def decisions(self, ticket_id: str, *specs: DecisionRowSpec) -> None:
        """Insert several staff decisions about one ticket."""
        for spec in specs:
            await self.decision(ticket_id, spec)

    async def escalation(
        self,
        ticket_id: str,
        escalated_at: datetime,
        *staff_reason_codes: str,
        note: str | None = None,
    ) -> None:
        """Insert the escalation of a ticket."""
        await self._builder.execute(
            insert(EscalationRow).values(
                escalation_id=self._builder.next_uuid(),
                ticket_id=ticket_id,
                staff_reason_codes=list(staff_reason_codes),
                escalated_by_account_id=self._staff_account_id,
                escalated_at=escalated_at,
                note=note,
            )
        )

    async def escalated_tickets(self, *specs: EscalationRowSpec) -> None:
        """Insert one escalated ticket with its escalation per spec."""
        for spec in specs:
            ticket_id = await self.ticket(
                imported_ticket(created_at=spec.escalated_at, status="escalated")
            )
            await self.escalation(ticket_id, spec.escalated_at, *spec.staff_reason_codes)

    async def reply(
        self, ticket_id: str, suggestion_id: UUID, sent_at: datetime, body: str, note: str
    ) -> None:
        """Insert the reply of a ticket, sent from its AI draft, with a note."""
        await self._builder.execute(
            insert(ReplyRow).values(
                reply_id=self._builder.next_uuid(),
                ticket_id=ticket_id,
                basis="ai_draft",
                suggestion_id=suggestion_id,
                acknowledged_warning_ids=[],
                staff_reason_codes=[],
                sent_by_account_id=self._staff_account_id,
                sent_at=sent_at,
                body=body,
                note=note,
            )
        )

    async def map_entry(self, ticket_id: str, pseudonym: str, original_value: str) -> None:
        """Insert one entry of a ticket's pseudonym map."""
        await self._builder.execute(
            text(_INSERT_MAP_ENTRY).bindparams(
                ticket_id=ticket_id,
                pseudonym=pseudonym,
                original_value=original_value,
                created_at=START_AT,
            )
        )
