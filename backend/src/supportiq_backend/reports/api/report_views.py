"""The mapping of a report to the contract's `ConsoleReport` (ARCH-15).

A share, a percentile, or an average that the domain left absent stays absent: the contract
never uses `null` (CON-08).
"""

from pydantic import MISSING

from supportiq_backend.generated import (
    AiErrorRate as ContractAiErrorRate,
)
from supportiq_backend.generated import (
    AiOutcomes as ContractAiOutcomes,
)
from supportiq_backend.generated import (
    AiReasonCode as ContractAiReasonCode,
)
from supportiq_backend.generated import (
    ByDraftStatu,
    ByReasonCodeItem,
    ByReasonItem,
    CompletedDraftStatus,
    LlmCostMicroUsd,
    Period,
    StaffReasonReplyCount,
)
from supportiq_backend.generated import (
    ConsoleReport as ContractConsoleReport,
)
from supportiq_backend.generated import (
    DraftDecisions as ContractDraftDecisions,
)
from supportiq_backend.generated import (
    EndToEndLatency as ContractEndToEndLatency,
)
from supportiq_backend.generated import (
    Escalations as ContractEscalations,
)
from supportiq_backend.generated import (
    HandlingTime as ContractHandlingTime,
)
from supportiq_backend.generated import (
    ModeCounts as ContractModeCounts,
)
from supportiq_backend.generated import (
    ModeHandlingTime as ContractModeHandlingTime,
)
from supportiq_backend.generated import (
    StaffReasonCode as ContractStaffReasonCode,
)
from supportiq_backend.generated import (
    TicketCounts as ContractTicketCounts,
)
from supportiq_backend.platform.web import format_timestamp
from supportiq_backend.reports.domain import (
    AiErrorRate,
    AiOutcomes,
    CodeCount,
    ConsoleReport,
    DraftDecisions,
    EndToEndLatency,
    Escalations,
    HandlingTime,
    LlmCost,
    ModeCounts,
    ModeHandlingTime,
    TicketCounts,
)
from supportiq_backend.tickets import StaffReasonCode


def to_console_report(report: ConsoleReport) -> ContractConsoleReport:
    """Map a report to the contract.

    Args:
        report: The report.

    Returns:
        The contract model.
    """
    return ContractConsoleReport(
        period=Period(
            start_at=format_timestamp(report.period.start_at),
            end_at=format_timestamp(report.period.end_at),
        ),
        ticket_counts=_to_ticket_counts(report.ticket_counts),
        draft_decisions=_to_draft_decisions(report.draft_decisions),
        escalations=_to_escalations(report.escalations),
        ai_outcomes=_to_ai_outcomes(report.ai_outcomes),
        end_to_end_latency=_to_end_to_end_latency(report.end_to_end_latency),
        ai_error_rate=_to_ai_error_rate(report.ai_error_rate),
        llm_cost_micro_usd=_to_llm_cost(report.llm_cost),
        handling_time=_to_handling_time(report.handling_time),
    )


def _to_ticket_counts(counts: TicketCounts) -> ContractTicketCounts:
    return ContractTicketCounts(
        created=_to_mode_counts(counts.created), closed=_to_mode_counts(counts.closed)
    )


def _to_mode_counts(counts: ModeCounts) -> ContractModeCounts:
    return ContractModeCounts(
        assisted_count=counts.assisted_count, manual_count=counts.manual_count
    )


def _to_draft_decisions(decisions: DraftDecisions) -> ContractDraftDecisions:
    return ContractDraftDecisions(
        approve_count=decisions.approve_count,
        edit_count=decisions.edit_count,
        reject_count=decisions.reject_count,
        edit_by_reason=_to_reply_counts(decisions.edit_by_reason),
        reject_by_reason=_to_reply_counts(decisions.reject_by_reason),
        approve_share=_or_missing(decisions.approve_share),
        edit_share=_or_missing(decisions.edit_share),
        reject_share=_or_missing(decisions.reject_share),
    )


def _to_reply_counts(
    items: tuple[CodeCount[StaffReasonCode], ...],
) -> list[StaffReasonReplyCount]:
    return [
        StaffReasonReplyCount(
            staff_reason_code=ContractStaffReasonCode(item.code.value), reply_count=item.count
        )
        for item in items
    ]


def _to_escalations(escalations: Escalations) -> ContractEscalations:
    return ContractEscalations(
        escalation_count=escalations.escalation_count,
        by_reason=[
            ByReasonItem(
                staff_reason_code=ContractStaffReasonCode(item.code.value),
                escalation_count=item.count,
            )
            for item in escalations.by_reason
        ],
    )


def _to_ai_outcomes(outcomes: AiOutcomes) -> ContractAiOutcomes:
    return ContractAiOutcomes(
        by_draft_status=[
            ByDraftStatu(
                draft_status=CompletedDraftStatus(item.code.value), suggestion_count=item.count
            )
            for item in outcomes.by_draft_status
        ],
        by_reason_code=[
            ByReasonCodeItem(
                reason_code=ContractAiReasonCode(item.code.value), suggestion_count=item.count
            )
            for item in outcomes.by_reason_code
        ],
    )


def _to_end_to_end_latency(latency: EndToEndLatency) -> ContractEndToEndLatency:
    percentiles = latency.percentiles
    if percentiles is None:
        return ContractEndToEndLatency(ticket_count=latency.ticket_count)
    return ContractEndToEndLatency(
        ticket_count=latency.ticket_count,
        p50_ms=percentiles.p50_ms,
        p95_ms=percentiles.p95_ms,
    )


def _to_ai_error_rate(rate: AiErrorRate) -> ContractAiErrorRate:
    return ContractAiErrorRate(
        suggestion_count=rate.suggestion_count,
        failed_count=rate.failed_count,
        share=_or_missing(rate.share),
    )


def _to_llm_cost(cost: LlmCost) -> LlmCostMicroUsd:
    return LlmCostMicroUsd(
        total=cost.total_micro_usd,
        llm_call_count=cost.llm_call_count,
        average=_or_missing(cost.average_micro_usd),
    )


def _to_handling_time(handling_time: HandlingTime) -> ContractHandlingTime:
    return ContractHandlingTime(
        assisted=_to_mode_handling_time(handling_time.assisted),
        manual=_to_mode_handling_time(handling_time.manual),
    )


def _to_mode_handling_time(mode: ModeHandlingTime) -> ContractModeHandlingTime:
    return ContractModeHandlingTime(ticket_count=mode.ticket_count, p50_ms=_or_missing(mode.p50_ms))


def _or_missing[ValueT: (int, float)](value: ValueT | None) -> ValueT | MISSING:
    return MISSING if value is None else value
