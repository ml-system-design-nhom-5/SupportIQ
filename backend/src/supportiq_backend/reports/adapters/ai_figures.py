"""The `AiFigures` port on `suggestion_parts`, `suggestions`, and `tickets`.

Each figure is one read-only aggregate over the period, and the breakdown by AI reason code is
one more, over the JSON array of codes expanded by `code_arrays`. A part is completed when it
left `pending`, which its `completed_at` records; a suggestion is completed when its last part
is (backend ticket workflow design, Reports).
"""

from decimal import Decimal

from sqlalchemy import ColumnElement, Subquery, and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.platform.persistence import parse_stored_enum
from supportiq_backend.reports.adapters.code_arrays import CODE_COLUMN, expand_codes, join_codes
from supportiq_backend.reports.adapters.sql_periods import (
    in_period,
    median_ms,
    p95_ms,
    to_optional_milliseconds,
)
from supportiq_backend.reports.adapters.tables import SUGGESTION_PARTS, SUGGESTIONS, TICKETS
from supportiq_backend.reports.domain import (
    AiErrorRate,
    AiOutcomes,
    EndToEndLatency,
    LatencyPercentiles,
    LlmCost,
    ReportPeriod,
)
from supportiq_backend.suggestions import AiReasonCode, PartStatus, SuggestionPart

_DRAFT = SuggestionPart.DRAFT.value
_CANCELLED = PartStatus.CANCELLED.value
# A failed suggestion has a part `unavailable` or a draft `llm_unavailable`; only a draft part
# can be `llm_unavailable` (the check constraint of `r0003`).
_FAILED_STATUSES = (PartStatus.UNAVAILABLE.value, PartStatus.LLM_UNAVAILABLE.value)
_PART_CODES = "part_codes"


class PostgresAiFigures:
    """Implement the `AiFigures` port in the read transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the report's transaction.
        """
        self._session = session

    async def load_ai_outcomes(self, period: ReportPeriod) -> AiOutcomes:
        """Count the draft parts completed in the period, without `cancelled` parts.

        Args:
            period: The period.

        Returns:
            The counts by status and by AI reason code.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        is_counted = and_(_is_draft_completed_in(period), SUGGESTION_PARTS.c.status != _CANCELLED)
        statuses = await self._session.execute(
            select(SUGGESTION_PARTS.c.status, func.count())
            .where(is_counted)
            .group_by(SUGGESTION_PARTS.c.status)
        )
        expanded = expand_codes(SUGGESTION_PARTS.c.reason_codes, _PART_CODES)
        code = expanded.c[CODE_COLUMN]
        codes = await self._session.execute(
            select(code, func.count())
            .select_from(join_codes(SUGGESTION_PARTS, expanded))
            .where(is_counted)
            .group_by(code)
        )
        return AiOutcomes(
            count_by_draft_status={
                parse_stored_enum(PartStatus, status): count for status, count in statuses.tuples()
            },
            count_by_reason_code={
                parse_stored_enum(AiReasonCode, name): count for name, count in codes.tuples()
            },
        )

    async def load_end_to_end_latency(self, period: ReportPeriod) -> EndToEndLatency:
        """Measure the latency of the first draft of each ticket, for those completed in it.

        The first suggestion of a ticket is its oldest; the latency runs from the ticket's
        `created_at` to the `completed_at` of that suggestion's draft part (NFR-08). A ticket
        whose first draft was `cancelled` gave staff no result, so it is left out; an
        `unavailable` or `llm_unavailable` first draft is a result, so it counts (contract
        `ConsoleReport.end_to_end_latency`). A draft that replaced a cancelled one is never a
        first draft.

        Args:
            period: The period.

        Returns:
            The number of tickets and the percentiles.
        """
        first = _first_suggestions()
        latency = SUGGESTION_PARTS.c.completed_at - TICKETS.c.created_at
        result = await self._session.execute(
            select(func.count(), median_ms(latency), p95_ms(latency))
            .select_from(first)
            .join(SUGGESTION_PARTS, SUGGESTION_PARTS.c.suggestion_id == first.c.suggestion_id)
            .join(TICKETS, TICKETS.c.ticket_id == first.c.ticket_id)
            .where(_is_draft_completed_in(period), SUGGESTION_PARTS.c.status != _CANCELLED)
        )
        ticket_count, median, p95 = result.tuples().one()
        return EndToEndLatency(ticket_count, _to_percentiles(median, p95))

    async def load_ai_error_rate(self, period: ReportPeriod) -> AiErrorRate:
        """Count the suggestions completed in the period, and those that failed.

        A suggestion with a `cancelled` part was superseded, so it is not counted.

        Args:
            period: The period.

        Returns:
            The counts.
        """
        completed = _completed_suggestions()
        result = await self._session.execute(
            select(func.count(), func.count().filter(completed.c.has_failed)).where(
                in_period(completed.c.completed_at, period)
            )
        )
        suggestion_count, failed_count = result.tuples().one()
        return AiErrorRate(suggestion_count, failed_count)

    async def load_llm_cost(self, period: ReportPeriod) -> LlmCost:
        """Sum the LLM cost of the draft parts completed in the period.

        A part without a cost made no LLM call that was answered, so `count` of the column is
        the number of LLM calls.

        Args:
            period: The period.

        Returns:
            The total and the number of LLM calls.
        """
        cost = SUGGESTION_PARTS.c.llm_cost_micro_usd
        result = await self._session.execute(
            select(func.coalesce(func.sum(cost), 0), func.count(cost)).where(
                _is_draft_completed_in(period)
            )
        )
        total, llm_call_count = result.tuples().one()
        return LlmCost(int(total), llm_call_count)


def _is_draft_completed_in(period: ReportPeriod) -> ColumnElement[bool]:
    return and_(
        SUGGESTION_PARTS.c.part == _DRAFT, in_period(SUGGESTION_PARTS.c.completed_at, period)
    )


def _first_suggestions() -> Subquery:
    # The oldest suggestion of each ticket, with `DISTINCT ON`; the ID breaks a tie.
    return (
        select(SUGGESTIONS.c.suggestion_id, SUGGESTIONS.c.ticket_id)
        .distinct(SUGGESTIONS.c.ticket_id)
        .order_by(SUGGESTIONS.c.ticket_id, SUGGESTIONS.c.created_at, SUGGESTIONS.c.suggestion_id)
        .subquery("first_suggestions")
    )


def _completed_suggestions() -> Subquery:
    # Every suggestion without a pending or a cancelled part, with the time of its last part.
    parts = SUGGESTION_PARTS.c
    return (
        select(
            func.max(parts.completed_at).label("completed_at"),
            func.bool_or(parts.status.in_(_FAILED_STATUSES)).label("has_failed"),
        )
        .group_by(parts.suggestion_id)
        .having(
            func.bool_and(parts.completed_at.is_not(None)),
            not_(func.bool_or(parts.status == _CANCELLED)),
        )
        .subquery("completed_suggestions")
    )


def _to_percentiles(median: Decimal | None, p95: Decimal | None) -> LatencyPercentiles | None:
    # `percentile_cont` is NULL exactly when no ticket was measured.
    median_milliseconds = to_optional_milliseconds(median)
    p95_milliseconds = to_optional_milliseconds(p95)
    if median_milliseconds is None or p95_milliseconds is None:
        return None
    return LatencyPercentiles(median_milliseconds, p95_milliseconds)
