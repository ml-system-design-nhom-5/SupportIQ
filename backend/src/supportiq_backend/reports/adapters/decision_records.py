"""The `DecisionRecordSource` port: the records of `backend export-decisions` (SEC-33).

Four queries per export, whatever the number of tickets: the tickets closed or escalated in the
period, the parts of their current suggestions, those suggestions, and their staff decisions.
Text comes only from the stored AI exchange, which holds placeholders: `request ->> 'message'`,
the message as sent, and the allow-listed fields of each part's result. No query reads a reply, a
note, a customer message, or the pseudonym map; `tables` does not even declare them (SEC-37).
"""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import Row, Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.platform import UnexpectedFailureError
from supportiq_backend.platform.persistence import (
    parse_optional_stored_enum,
    parse_stored_enum,
)
from supportiq_backend.reports.adapters.sql_periods import (
    handling_duration,
    in_period,
    to_optional_milliseconds,
    to_whole_milliseconds,
)
from supportiq_backend.reports.adapters.tables import (
    ESCALATIONS,
    STAFF_DECISIONS,
    SUGGESTION_PARTS,
    SUGGESTIONS,
    TICKETS,
)
from supportiq_backend.reports.domain import (
    DecisionRecord,
    ExportedDecision,
    ExportedPart,
    JsonValue,
    ReportPeriod,
    SuggestionSnapshot,
)
from supportiq_backend.suggestions import (
    AiReasonCode,
    IntentLabel,
    PartStatus,
    SuggestionId,
    SuggestionPart,
    SuggestionTrigger,
)
from supportiq_backend.tickets import DecisionType, HandlingMode, StaffReasonCode, TicketId

# The fields of an ai-service response that the evaluation needs (SEC-33), by part. The draft
# part leaves out its embedded analysis, which the analysis part already holds, the AI's staff
# note, and the latencies, masks, and LLM usage, which the report covers.
_RESULT_FIELDS_BY_PART: Mapping[SuggestionPart, tuple[str, ...]] = {
    SuggestionPart.ANALYSIS: (
        "intent",
        "alternatives",
        "is_in_scope",
        "documents",
        "routing",
        "warnings",
        "versions",
    ),
    SuggestionPart.DRAFT: ("draft", "versions"),
}
_MESSAGE_FIELD = "message"

type _TicketColumns = tuple[
    str,
    str,
    str | None,
    str | None,
    datetime,
    datetime | None,
    datetime | None,
    datetime | None,
    UUID | None,
    # The handling time is NULL for a ticket that is not closed, was never viewed, or was first
    # viewed after its reply; the types of SQL expressions do not carry nullability, so
    # `to_optional_milliseconds` handles it.
    Decimal,
]
type _SuggestionColumns = tuple[UUID, str, str | None, datetime, str | None]
type _PartColumns = tuple[UUID, str, str, object, datetime | None, object]
type _DecisionColumns = tuple[str, str, object, float | None, str | None, bool | None, datetime]


class PostgresDecisionRecordSource:
    """Implement the `DecisionRecordSource` port in the read transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the export's transaction.
        """
        self._session = session

    async def load_decision_records(self, period: ReportPeriod) -> tuple[DecisionRecord, ...]:
        """Load one record per ticket closed or escalated in the period.

        Args:
            period: The period.

        Returns:
            The records, in the order of the ticket numbers.

        Raises:
            UnexpectedFailureError: A stored JSON value does not have the shape that backend
                writes, or a stored text is no value of its enum: a defect.
        """
        tickets = (await self._session.execute(_select_tickets(period))).all()
        snapshots = await self._load_snapshots(
            frozenset(
                row.current_suggestion_id
                for row in tickets
                if row.current_suggestion_id is not None
            )
        )
        decisions = await self._load_decisions(frozenset(row.ticket_id for row in tickets))
        return tuple(_to_record(row, snapshots, decisions) for row in tickets)

    async def _load_snapshots(
        self, suggestion_ids: frozenset[UUID]
    ) -> Mapping[UUID, SuggestionSnapshot]:
        if not suggestion_ids:
            return {}
        parts = await self._session.execute(_select_parts(suggestion_ids))
        part_by_key = {
            (row.suggestion_id, parse_stored_enum(SuggestionPart, row.part)): _to_part(row)
            for row in parts
        }
        suggestions = await self._session.execute(_select_suggestions(suggestion_ids))
        return {row.suggestion_id: _to_snapshot(row, part_by_key) for row in suggestions}

    async def _load_decisions(
        self, ticket_ids: frozenset[str]
    ) -> Mapping[str, tuple[ExportedDecision, ...]]:
        if not ticket_ids:
            return {}
        rows = await self._session.execute(_select_decisions(ticket_ids))
        decisions_by_ticket: dict[str, list[ExportedDecision]] = {}
        for row in rows:
            decisions_by_ticket.setdefault(row.ticket_id, []).append(_to_decision(row))
        return {ticket_id: tuple(found) for ticket_id, found in decisions_by_ticket.items()}


def _select_tickets(period: ReportPeriod) -> Select[_TicketColumns]:
    handling_time = to_whole_milliseconds(handling_duration())
    is_closed_or_escalated = or_(
        in_period(TICKETS.c.closed_at, period), in_period(ESCALATIONS.c.escalated_at, period)
    )
    return (
        select(
            TICKETS.c.ticket_id,
            TICKETS.c.handling_mode,
            TICKETS.c.study_pair_id,
            TICKETS.c.study_batch,
            TICKETS.c.created_at,
            TICKETS.c.handling_started_at,
            ESCALATIONS.c.escalated_at,
            TICKETS.c.closed_at,
            TICKETS.c.current_suggestion_id,
            handling_time.label("handling_time_ms"),
        )
        .select_from(TICKETS)
        .outerjoin(ESCALATIONS, ESCALATIONS.c.ticket_id == TICKETS.c.ticket_id)
        .where(is_closed_or_escalated)
        .order_by(TICKETS.c.ticket_number)
    )


def _select_suggestions(suggestion_ids: frozenset[UUID]) -> Select[_SuggestionColumns]:
    # Only the message of the stored request: its order context is not needed (SEC-33).
    message = SUGGESTIONS.c.request[_MESSAGE_FIELD].astext
    return select(
        SUGGESTIONS.c.suggestion_id,
        SUGGESTIONS.c.trigger,
        SUGGESTIONS.c.intent_override,
        SUGGESTIONS.c.created_at,
        message.label("pseudonymized_message"),
    ).where(SUGGESTIONS.c.suggestion_id.in_(suggestion_ids))


def _select_parts(suggestion_ids: frozenset[UUID]) -> Select[_PartColumns]:
    return select(
        SUGGESTION_PARTS.c.suggestion_id,
        SUGGESTION_PARTS.c.part,
        SUGGESTION_PARTS.c.status,
        SUGGESTION_PARTS.c.reason_codes,
        SUGGESTION_PARTS.c.completed_at,
        SUGGESTION_PARTS.c.result,
    ).where(SUGGESTION_PARTS.c.suggestion_id.in_(suggestion_ids))


def _select_decisions(ticket_ids: frozenset[str]) -> Select[_DecisionColumns]:
    return (
        select(
            STAFF_DECISIONS.c.ticket_id,
            STAFF_DECISIONS.c.decision_type,
            STAFF_DECISIONS.c.staff_reason_codes,
            STAFF_DECISIONS.c.change_ratio,
            STAFF_DECISIONS.c.final_intent,
            STAFF_DECISIONS.c.is_proposal_changed,
            STAFF_DECISIONS.c.decided_at,
        )
        .where(STAFF_DECISIONS.c.ticket_id.in_(ticket_ids))
        .order_by(STAFF_DECISIONS.c.decided_at, STAFF_DECISIONS.c.decision_id)
    )


def _to_record(
    row: Row[_TicketColumns],
    snapshots: Mapping[UUID, SuggestionSnapshot],
    decisions: Mapping[str, tuple[ExportedDecision, ...]],
) -> DecisionRecord:
    suggestion_id = row.current_suggestion_id
    return DecisionRecord(
        ticket_id=TicketId(row.ticket_id),
        handling_mode=parse_stored_enum(HandlingMode, row.handling_mode),
        study_pair_id=row.study_pair_id,
        study_batch=row.study_batch,
        created_at=row.created_at,
        handling_started_at=row.handling_started_at,
        escalated_at=row.escalated_at,
        closed_at=row.closed_at,
        handling_time_ms=to_optional_milliseconds(row.handling_time_ms),
        # The foreign key of `tickets.current_suggestion_id` makes the suggestion present.
        suggestion=None if suggestion_id is None else snapshots[suggestion_id],
        decisions=decisions.get(row.ticket_id, ()),
    )


def _to_snapshot(
    row: Row[_SuggestionColumns],
    part_by_key: Mapping[tuple[UUID, SuggestionPart], ExportedPart],
) -> SuggestionSnapshot:
    return SuggestionSnapshot(
        suggestion_id=SuggestionId(str(row.suggestion_id)),
        trigger=parse_stored_enum(SuggestionTrigger, row.trigger),
        intent_override=parse_optional_stored_enum(IntentLabel, row.intent_override),
        created_at=row.created_at,
        pseudonymized_message=row.pseudonymized_message,
        # Every suggestion is inserted with both parts (backend ticket workflow design, Tables).
        analysis=part_by_key[(row.suggestion_id, SuggestionPart.ANALYSIS)],
        draft=part_by_key[(row.suggestion_id, SuggestionPart.DRAFT)],
    )


def _to_part(row: Row[_PartColumns]) -> ExportedPart:
    return ExportedPart(
        status=parse_stored_enum(PartStatus, row.status),
        reason_codes=tuple(
            parse_stored_enum(AiReasonCode, code) for code in _as_texts(row.reason_codes)
        ),
        completed_at=row.completed_at,
        result_fields=_select_result_fields(
            parse_stored_enum(SuggestionPart, row.part), row.result
        ),
    )


def _to_decision(row: Row[_DecisionColumns]) -> ExportedDecision:
    return ExportedDecision(
        decision_type=parse_stored_enum(DecisionType, row.decision_type),
        staff_reason_codes=tuple(
            parse_stored_enum(StaffReasonCode, code) for code in _as_texts(row.staff_reason_codes)
        ),
        change_ratio=row.change_ratio,
        final_intent=parse_optional_stored_enum(IntentLabel, row.final_intent),
        is_proposal_changed=row.is_proposal_changed,
        decided_at=row.decided_at,
    )


def _select_result_fields(part: SuggestionPart, result: object) -> Mapping[str, JsonValue] | None:
    if result is None:
        return None
    if not isinstance(result, dict):
        raise UnexpectedFailureError
    # Boundary parsing: a `jsonb` object decodes to a dict with text keys and JSON values.
    stored = cast("dict[str, JsonValue]", result)
    return {name: stored[name] for name in _RESULT_FIELDS_BY_PART[part] if name in stored}


def _as_texts(codes: object) -> tuple[str, ...]:
    # The reason-code columns are JSON arrays of text, as the stores of tickets and suggestions
    # write them.
    if not isinstance(codes, list):
        raise UnexpectedFailureError
    return tuple(str(code) for code in cast("list[object]", codes))
