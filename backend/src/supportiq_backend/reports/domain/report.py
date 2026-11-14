"""The figures of the report of a period for managers (FR-10, NFR-11), and the report itself.

Each figure holds what the adapters counted in PostgreSQL over the period; `report_rules` decides
the order of its items, its shares, its average, and which values are absent because nothing was
counted (contracts v1 design, Reports; contract `ConsoleReport`). A report holds aggregates only:
no text and no ticket ID.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from supportiq_backend.reports.domain.report_rules import (
    CodeCount,
    ReportPeriod,
    compute_rounded_average,
    compute_share,
    order_code_counts,
)
from supportiq_backend.suggestions import AiReasonCode, PartStatus
from supportiq_backend.tickets import StaffReasonCode

# The statuses of a draft part that left `pending`, without `cancelled`, in the order of the
# contract's `CompletedDraftStatus`.
_COMPLETED_DRAFT_STATUSES = (
    PartStatus.DRAFT_READY,
    PartStatus.ABSTAINED,
    PartStatus.ESCALATION_RECOMMENDED,
    PartStatus.LLM_UNAVAILABLE,
    PartStatus.UNAVAILABLE,
)
# The contract orders reason-code items as its enums list the codes, as these enums do.
_STAFF_REASON_CODES = tuple(StaffReasonCode)
_AI_REASON_CODES = tuple(AiReasonCode)


@dataclass(frozen=True, slots=True)
class ModeCounts:
    """A number of tickets for each handling mode.

    Attributes:
        assisted_count: The tickets in `assisted` mode.
        manual_count: The tickets in `manual` mode.
    """

    assisted_count: int
    manual_count: int


@dataclass(frozen=True, slots=True)
class TicketCounts:
    """The tickets created and the tickets closed in the period, by handling mode.

    Attributes:
        created: Tickets whose `created_at` falls in the period.
        closed: Tickets whose `closed_at` falls in the period.
    """

    created: ModeCounts
    closed: ModeCounts


@dataclass(frozen=True, slots=True)
class DraftDecisions:
    """The staff decisions about a ready draft recorded in the period (ADR-0006).

    A decision with two staff reason codes counts once under each code.

    Attributes:
        approve_count: The `approve` decisions.
        edit_count: The `edit` decisions.
        reject_count: The `reject` decisions.
        edit_count_by_reason: The `edit` decisions by staff reason code.
        reject_count_by_reason: The `reject` decisions by staff reason code.
    """

    approve_count: int
    edit_count: int
    reject_count: int
    edit_count_by_reason: Mapping[StaffReasonCode, int]
    reject_count_by_reason: Mapping[StaffReasonCode, int]

    @property
    def edit_by_reason(self) -> tuple[CodeCount[StaffReasonCode], ...]:
        """Return the edits by reason code, in the order of `StaffReasonCode`."""
        return order_code_counts(self.edit_count_by_reason, _STAFF_REASON_CODES)

    @property
    def reject_by_reason(self) -> tuple[CodeCount[StaffReasonCode], ...]:
        """Return the rejections by reason code, in the order of `StaffReasonCode`."""
        return order_code_counts(self.reject_count_by_reason, _STAFF_REASON_CODES)

    @property
    def approve_share(self) -> float | None:
        """Return the share of approvals, from 0 to 1; None when no decision was counted."""
        return compute_share(self.approve_count, self._decision_count)

    @property
    def edit_share(self) -> float | None:
        """Return the share of edits, from 0 to 1; None when no decision was counted."""
        return compute_share(self.edit_count, self._decision_count)

    @property
    def reject_share(self) -> float | None:
        """Return the share of rejections, from 0 to 1; None when no decision was counted."""
        return compute_share(self.reject_count, self._decision_count)

    @property
    def _decision_count(self) -> int:
        return self.approve_count + self.edit_count + self.reject_count


@dataclass(frozen=True, slots=True)
class Escalations:
    """The escalations of the period, by staff reason code (FR-10).

    Attributes:
        escalation_count: The escalations; one with two codes counts once.
        count_by_reason: The escalations by staff reason code; one with two codes counts
            under each.
    """

    escalation_count: int
    count_by_reason: Mapping[StaffReasonCode, int]

    @property
    def by_reason(self) -> tuple[CodeCount[StaffReasonCode], ...]:
        """Return the escalations by reason code, in the order of `StaffReasonCode`."""
        return order_code_counts(self.count_by_reason, _STAFF_REASON_CODES)


@dataclass(frozen=True, slots=True)
class AiOutcomes:
    """The draft parts completed in the period, without `cancelled` parts.

    Attributes:
        count_by_draft_status: The draft parts by final status.
        count_by_reason_code: The draft parts by AI reason code; a part with two codes counts
            under each.
    """

    count_by_draft_status: Mapping[PartStatus, int]
    count_by_reason_code: Mapping[AiReasonCode, int]

    @property
    def by_draft_status(self) -> tuple[CodeCount[PartStatus], ...]:
        """Return the draft parts by status, in the order of `CompletedDraftStatus`.

        A status outside that list, such as `cancelled`, never appears.
        """
        return order_code_counts(self.count_by_draft_status, _COMPLETED_DRAFT_STATUSES)

    @property
    def by_reason_code(self) -> tuple[CodeCount[AiReasonCode], ...]:
        """Return the draft parts by reason code, in the order of `AiReasonCode`."""
        return order_code_counts(self.count_by_reason_code, _AI_REASON_CODES)


@dataclass(frozen=True, slots=True)
class LatencyPercentiles:
    """Two percentiles of a duration, rounded to whole milliseconds.

    Attributes:
        p50_ms: The median.
        p95_ms: The 95th percentile.
    """

    p50_ms: int
    p95_ms: int


@dataclass(frozen=True, slots=True)
class EndToEndLatency:
    """From ticket creation until the draft part of its first suggestion left `pending` (NFR-08).

    Attributes:
        ticket_count: The tickets whose first draft part was completed in the period.
        percentiles: The percentiles; None exactly when `ticket_count` is 0.
    """

    ticket_count: int
    percentiles: LatencyPercentiles | None


@dataclass(frozen=True, slots=True)
class AiErrorRate:
    """The suggestions completed in the period that failed (FR-10).

    Attributes:
        suggestion_count: The suggestions completed in the period without a `cancelled` part.
        failed_count: Those with a part `unavailable` or a draft `llm_unavailable`.
    """

    suggestion_count: int
    failed_count: int

    @property
    def share(self) -> float | None:
        """Return the share of failed suggestions, from 0 to 1; None when none was counted."""
        return compute_share(self.failed_count, self.suggestion_count)


@dataclass(frozen=True, slots=True)
class LlmCost:
    """The LLM cost of the draft parts completed in the period (FR-10, NFR-10).

    Attributes:
        total_micro_usd: The sum of the cost of every draft call, in micro-USD.
        llm_call_count: The draft parts whose call used the LLM.
    """

    total_micro_usd: int
    llm_call_count: int

    @property
    def average_micro_usd(self) -> int | None:
        """Return the average per LLM call, to the nearest micro-USD; None without a call."""
        return compute_rounded_average(self.total_micro_usd, self.llm_call_count)


@dataclass(frozen=True, slots=True)
class ModeHandlingTime:
    """The handling time of the tickets of one mode closed in the period (NFR-11).

    Attributes:
        ticket_count: The closed tickets of the mode first viewed no later than their reply.
        p50_ms: The median from the first view to the reply; None when `ticket_count` is 0.
    """

    ticket_count: int
    p50_ms: int | None


@dataclass(frozen=True, slots=True)
class HandlingTime:
    """The median handling time by handling mode (NFR-11).

    Attributes:
        assisted: The tickets in `assisted` mode.
        manual: The tickets in `manual` mode.
    """

    assisted: ModeHandlingTime
    manual: ModeHandlingTime


@dataclass(frozen=True, slots=True)
class ConsoleReport:
    """The figures of FR-10 and NFR-11 for one period, from backend's own records (LOG-33).

    Attributes:
        period: The period, as requested.
        ticket_counts: Tickets created and closed.
        draft_decisions: The decisions about ready drafts.
        escalations: The escalations.
        ai_outcomes: The completed draft parts.
        end_to_end_latency: The latency of the first draft of each ticket.
        ai_error_rate: The share of failed suggestions.
        llm_cost: The LLM cost.
        handling_time: The handling time by mode.
    """

    period: ReportPeriod
    ticket_counts: TicketCounts
    draft_decisions: DraftDecisions
    escalations: Escalations
    ai_outcomes: AiOutcomes
    end_to_end_latency: EndToEndLatency
    ai_error_rate: AiErrorRate
    llm_cost: LlmCost
    handling_time: HandlingTime
