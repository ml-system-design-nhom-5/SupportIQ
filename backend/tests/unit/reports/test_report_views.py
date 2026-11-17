"""The mapping of a report to the contract `ConsoleReport`: absent values stay absent (CON-08)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from supportiq_backend.platform.web import render_json
from supportiq_backend.reports import (
    AiErrorRate,
    AiOutcomes,
    ConsoleReport,
    DraftDecisions,
    EndToEndLatency,
    Escalations,
    HandlingTime,
    LlmCost,
    ModeCounts,
    ModeHandlingTime,
    TicketCounts,
    build_report_period,
)
from supportiq_backend.reports.api.report_views import to_console_report
from tests.unit.reports.fakes import (
    AI_OUTCOMES,
    CLOSED,
    CREATED,
    DRAFT_DECISIONS,
    ERROR_RATE,
    ESCALATIONS,
    HANDLING_TIME,
    LATENCY,
    LLM_COST,
    PERIOD,
)

EXAMPLES = Path(__file__).parents[4] / "contracts/examples/getConsoleReport"
NO_TICKETS = ModeCounts(assisted_count=0, manual_count=0)
NOT_MEASURED = ModeHandlingTime(ticket_count=0, p50_ms=None)
# The period of the example `empty-period`.
EMPTY_PERIOD = build_report_period(
    datetime(2026, 12, 1, tzinfo=UTC), datetime(2026, 12, 8, tzinfo=UTC)
)
EMPTY_REPORT = ConsoleReport(
    period=EMPTY_PERIOD,
    ticket_counts=TicketCounts(created=NO_TICKETS, closed=NO_TICKETS),
    draft_decisions=DraftDecisions(0, 0, 0, {}, {}),
    escalations=Escalations(0, {}),
    ai_outcomes=AiOutcomes({}, {}),
    end_to_end_latency=EndToEndLatency(0, None),
    ai_error_rate=AiErrorRate(0, 0),
    llm_cost=LlmCost(0, 0),
    handling_time=HandlingTime(assisted=NOT_MEASURED, manual=NOT_MEASURED),
)
REPORT = ConsoleReport(
    period=PERIOD,
    ticket_counts=TicketCounts(created=CREATED, closed=CLOSED),
    draft_decisions=DRAFT_DECISIONS,
    escalations=ESCALATIONS,
    ai_outcomes=AI_OUTCOMES,
    end_to_end_latency=LATENCY,
    ai_error_rate=ERROR_RATE,
    llm_cost=LLM_COST,
    handling_time=HANDLING_TIME,
)


def render(report: ConsoleReport) -> dict[str, object]:
    return json.loads(render_json(to_console_report(report)))


def test_empty_report_is_the_contract_example_of_an_empty_period() -> None:
    example = json.loads((EXAMPLES / "empty-period.json").read_text(encoding="utf-8"))

    body = render(EMPTY_REPORT)

    assert body == example["value"]


def test_report_writes_the_period_as_contract_timestamps() -> None:
    body = render(REPORT)

    assert body["period"] == {"start_at": "2026-11-02T00:00:00Z", "end_at": "2026-11-09T00:00:00Z"}


def test_report_writes_draft_decisions_with_shares_and_ordered_reasons() -> None:
    body = render(REPORT)

    assert body["draft_decisions"] == {
        "approve_count": 1,
        "edit_count": 2,
        "reject_count": 1,
        "edit_by_reason": [
            {"staff_reason_code": "wrong_source", "reply_count": 1},
            {"staff_reason_code": "tone_or_clarity", "reply_count": 1},
        ],
        "reject_by_reason": [{"staff_reason_code": "kb_gap", "reply_count": 1}],
        "approve_share": 0.25,
        "edit_share": 0.5,
        "reject_share": 0.25,
    }


def test_report_writes_ai_figures_with_percentiles_share_and_average() -> None:
    body = render(REPORT)

    assert (
        body["ai_outcomes"],
        body["end_to_end_latency"],
        body["ai_error_rate"],
        body["llm_cost_micro_usd"],
    ) == (
        {
            "by_draft_status": [
                {"draft_status": "draft_ready", "suggestion_count": 2},
                {"draft_status": "unavailable", "suggestion_count": 1},
            ],
            "by_reason_code": [{"reason_code": "ai_service_unavailable", "suggestion_count": 1}],
        },
        {"ticket_count": 4, "p50_ms": 3_600, "p95_ms": 9_800},
        {"suggestion_count": 4, "failed_count": 1, "share": 0.25},
        {"total": 420, "llm_call_count": 2, "average": 210},
    )


def test_report_writes_the_handling_time_of_each_mode_without_an_absent_median() -> None:
    body = render(REPORT)

    assert body["handling_time"] == {
        "assisted": {"ticket_count": 2, "p50_ms": 1_050_000},
        "manual": {"ticket_count": 0},
    }
