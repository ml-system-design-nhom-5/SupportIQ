"""The `TicketFigures` port on `tickets`, `staff_decisions`, and `escalations`.

Each figure is one read-only aggregate over the period, and a breakdown by staff reason code is
one more, over the JSON array of codes expanded by `code_arrays`, so a record with two codes
counts once under each (backend ticket workflow design, Reports).
"""

from collections.abc import Mapping, Sequence

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.platform.persistence import parse_stored_enum
from supportiq_backend.reports.adapters.code_arrays import CODE_COLUMN, expand_codes, join_codes
from supportiq_backend.reports.adapters.sql_periods import (
    handling_duration,
    in_period,
    median_ms,
    to_optional_milliseconds,
)
from supportiq_backend.reports.adapters.tables import ESCALATIONS, STAFF_DECISIONS, TICKETS
from supportiq_backend.reports.domain import (
    DraftDecisions,
    Escalations,
    HandlingTime,
    ModeCounts,
    ModeHandlingTime,
    ReportPeriod,
    TicketCounts,
)
from supportiq_backend.tickets import DecisionType, HandlingMode, StaffReasonCode

# The decisions about a ready draft; `escalate` is counted under escalations instead.
_DRAFT_DECISION_TYPES = (
    DecisionType.APPROVE.value,
    DecisionType.EDIT.value,
    DecisionType.REJECT.value,
)
_DECISION_TYPES_WITH_REASONS = (DecisionType.EDIT.value, DecisionType.REJECT.value)
_NO_HANDLING_TIME = ModeHandlingTime(ticket_count=0, p50_ms=None)
_DECISION_CODES = "decision_codes"
_ESCALATION_CODES = "escalation_codes"


class PostgresTicketFigures:
    """Implement the `TicketFigures` port in the read transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the report's transaction.
        """
        self._session = session

    async def load_ticket_counts(self, period: ReportPeriod) -> TicketCounts:
        """Count the tickets created and the tickets closed in the period, by handling mode.

        Args:
            period: The period.

        Returns:
            The counts.

        Raises:
            UnexpectedFailureError: A stored handling mode is no value of its enum: a defect.
        """
        is_created = in_period(TICKETS.c.created_at, period)
        is_closed = in_period(TICKETS.c.closed_at, period)
        rows = await self._session.execute(
            select(
                TICKETS.c.handling_mode,
                func.count().filter(is_created),
                func.count().filter(is_closed),
            )
            .where(or_(is_created, is_closed))
            .group_by(TICKETS.c.handling_mode)
        )
        counts = rows.tuples().all()
        return TicketCounts(
            created=_to_mode_counts(
                {parse_stored_enum(HandlingMode, mode): created for mode, created, _ in counts}
            ),
            closed=_to_mode_counts(
                {parse_stored_enum(HandlingMode, mode): closed for mode, _, closed in counts}
            ),
        )

    async def load_handling_time(self, period: ReportPeriod) -> HandlingTime:
        """Measure the median handling time of the tickets closed in the period, by mode.

        Only a ticket first viewed no later than its reply counts: the handling clock starts at
        the first view (NFR-11), and `handling_duration` is NULL for every other ticket.

        Args:
            period: The period.

        Returns:
            The handling time of each mode.

        Raises:
            UnexpectedFailureError: A stored handling mode is no value of its enum: a defect.
        """
        duration = handling_duration()
        # `count` of the duration counts the tickets that have one; the median ignores NULL.
        rows = await self._session.execute(
            select(TICKETS.c.handling_mode, func.count(duration), median_ms(duration))
            .where(in_period(TICKETS.c.closed_at, period))
            .group_by(TICKETS.c.handling_mode)
        )
        time_by_mode = {
            parse_stored_enum(HandlingMode, mode): ModeHandlingTime(
                count, to_optional_milliseconds(median)
            )
            for mode, count, median in rows.tuples()
        }
        return HandlingTime(
            assisted=time_by_mode.get(HandlingMode.ASSISTED, _NO_HANDLING_TIME),
            manual=time_by_mode.get(HandlingMode.MANUAL, _NO_HANDLING_TIME),
        )

    async def load_draft_decisions(self, period: ReportPeriod) -> DraftDecisions:
        """Count the `approve`, `edit`, and `reject` decisions of the period.

        Args:
            period: The period.

        Returns:
            The counts, overall and by staff reason code.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        is_decided = in_period(STAFF_DECISIONS.c.decided_at, period)
        count_by_type = await self._load_count_by_decision_type(is_decided)
        reason_counts = await self._load_reason_counts_of_decisions(is_decided)
        return DraftDecisions(
            approve_count=count_by_type.get(DecisionType.APPROVE, 0),
            edit_count=count_by_type.get(DecisionType.EDIT, 0),
            reject_count=count_by_type.get(DecisionType.REJECT, 0),
            edit_count_by_reason=_count_by_reason(reason_counts, DecisionType.EDIT),
            reject_count_by_reason=_count_by_reason(reason_counts, DecisionType.REJECT),
        )

    async def load_escalations(self, period: ReportPeriod) -> Escalations:
        """Count the escalations of the period.

        Args:
            period: The period.

        Returns:
            The counts, overall and by staff reason code.

        Raises:
            UnexpectedFailureError: A stored reason code is no value of its enum: a defect.
        """
        is_escalated = in_period(ESCALATIONS.c.escalated_at, period)
        total = await self._session.scalar(
            select(func.count()).select_from(ESCALATIONS).where(is_escalated)
        )
        codes = expand_codes(ESCALATIONS.c.staff_reason_codes, _ESCALATION_CODES)
        code = codes.c[CODE_COLUMN]
        by_reason = await self._session.execute(
            select(code, func.count())
            .select_from(join_codes(ESCALATIONS, codes))
            .where(is_escalated)
            .group_by(code)
        )
        return Escalations(
            escalation_count=total or 0,
            count_by_reason={
                parse_stored_enum(StaffReasonCode, reason): count
                for reason, count in by_reason.tuples()
            },
        )

    async def _load_count_by_decision_type(
        self, is_decided: ColumnElement[bool]
    ) -> Mapping[DecisionType, int]:
        decision_type = STAFF_DECISIONS.c.decision_type
        totals = await self._session.execute(
            select(decision_type, func.count())
            .where(is_decided, decision_type.in_(_DRAFT_DECISION_TYPES))
            .group_by(decision_type)
        )
        return {parse_stored_enum(DecisionType, name): count for name, count in totals.tuples()}

    async def _load_reason_counts_of_decisions(
        self, is_decided: ColumnElement[bool]
    ) -> Sequence[tuple[str, str, int]]:
        decision_type = STAFF_DECISIONS.c.decision_type
        codes = expand_codes(STAFF_DECISIONS.c.staff_reason_codes, _DECISION_CODES)
        code = codes.c[CODE_COLUMN]
        by_reason = await self._session.execute(
            select(decision_type, code, func.count())
            .select_from(join_codes(STAFF_DECISIONS, codes))
            .where(is_decided, decision_type.in_(_DECISION_TYPES_WITH_REASONS))
            .group_by(decision_type, code)
        )
        return by_reason.tuples().all()


def _count_by_reason(
    counts: Sequence[tuple[str, str, int]], decision_type: DecisionType
) -> Mapping[StaffReasonCode, int]:
    return {
        parse_stored_enum(StaffReasonCode, reason): count
        for name, reason, count in counts
        if parse_stored_enum(DecisionType, name) is decision_type
    }


def _to_mode_counts(count_by_mode: Mapping[HandlingMode, int]) -> ModeCounts:
    return ModeCounts(
        assisted_count=count_by_mode.get(HandlingMode.ASSISTED, 0),
        manual_count=count_by_mode.get(HandlingMode.MANUAL, 0),
    )
