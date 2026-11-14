"""The AI figures of `getConsoleReport` on fixed records with known answers, against PostgreSQL.

AI outcomes, end-to-end latency, AI error rate, and LLM cost; the ticket figures are in
`test_console_report_figures`. The period is [2026-11-02, 2026-11-09). For each figure, one test
inserts records on both sides of the bounds of the period: one at exactly `start_at`, which
counts, and one at exactly `end_at`, which does not. Any other test checks one rule. Suggestions
have a completed analysis part wherever a real one would, so a query that does not keep only the
draft parts counts too much (backend ticket workflow design, Reports and Testing).
"""

from datetime import datetime, timedelta

import pytest

from tests.integration.application import RunningBackend
from tests.integration.builders import SuggestionPartSpec, SuggestionSpec
from tests.integration.reports.report_rows import (
    BEFORE_START,
    END_AT,
    HOUR,
    MINUTE,
    START_AT,
    ReportRows,
    completed,
    imported_ticket,
    load_report,
)

pytestmark = pytest.mark.anyio

AI_SERVICE_UNAVAILABLE = "ai_service_unavailable"


def milliseconds(count: int) -> timedelta:
    return timedelta(milliseconds=count)


def suggestion_of(analysis: SuggestionPartSpec, draft: SuggestionPartSpec) -> SuggestionSpec:
    """Describe a suggestion created before the period, with its two parts."""
    return SuggestionSpec(created_at=BEFORE_START, analysis=analysis, draft=draft)


def with_ready_analysis(draft: SuggestionPartSpec) -> SuggestionSpec:
    """Describe a suggestion created before the period whose analysis was ready at `start_at`."""
    return suggestion_of(completed("ready", START_AT), draft)


def both_unavailable(completed_at: datetime) -> SuggestionSpec:
    """Describe a suggestion whose two parts ended `unavailable` because ai-service failed."""
    unavailable = completed("unavailable", completed_at, AI_SERVICE_UNAVAILABLE)
    return suggestion_of(unavailable, unavailable)


def retry_of(rows: ReportRows, created_at: datetime) -> SuggestionSpec:
    """Describe a retry that the staff account asked for, with a draft ready a minute later."""
    return SuggestionSpec(
        created_at=created_at,
        trigger="retry",
        requested_by_account_id=rows.staff_account_id,
        analysis=completed("ready", created_at),
        draft=completed("draft_ready", created_at + MINUTE),
    )


async def insert_ticket_whose_first_draft_was_cancelled(
    rows: ReportRows, created_at: datetime
) -> str:
    return await rows.ticket_with_first_suggestion(
        created_at,
        completed("ready", created_at + milliseconds(250)),
        completed("cancelled", created_at + milliseconds(500)),
    )


async def test_ai_outcomes_count_completed_drafts_by_status_and_code_without_cancelled_ones(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    ticket_id = await rows.ticket(imported_ticket(created_at=BEFORE_START))
    await rows.suggestions(
        ticket_id,
        with_ready_analysis(completed("draft_ready", START_AT)),
        with_ready_analysis(completed("abstained", START_AT + HOUR, "low_confidence")),
        with_ready_analysis(
            completed(
                "escalation_recommended",
                START_AT + 2 * HOUR,
                "requires_authority",
                "human_agent_requested",
            )
        ),
        # The analysis part has the same status and code as the draft part, and does not count.
        both_unavailable(START_AT + 3 * HOUR),
        # A reason code on a cancelled part, so the test proves that the query leaves it out.
        with_ready_analysis(completed("cancelled", START_AT + 4 * HOUR, "budget_exceeded")),
        with_ready_analysis(completed("draft_ready", END_AT)),
        with_ready_analysis(SuggestionPartSpec()),
    )

    report = await load_report(backend, manager_headers)

    assert report["ai_outcomes"] == {
        "by_draft_status": [
            {"draft_status": "draft_ready", "suggestion_count": 1},
            {"draft_status": "abstained", "suggestion_count": 1},
            {"draft_status": "escalation_recommended", "suggestion_count": 1},
            {"draft_status": "unavailable", "suggestion_count": 1},
        ],
        "by_reason_code": [
            {"reason_code": "low_confidence", "suggestion_count": 1},
            {"reason_code": "human_agent_requested", "suggestion_count": 1},
            {"reason_code": "requires_authority", "suggestion_count": 1},
            {"reason_code": "ai_service_unavailable", "suggestion_count": 1},
        ],
    }


async def test_ai_figures_of_a_period_with_only_a_cancelled_draft_count_nothing(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await insert_ticket_whose_first_draft_was_cancelled(rows, START_AT)

    report = await load_report(backend, manager_headers)

    assert (
        report["ai_outcomes"],
        report["end_to_end_latency"],
        report["ai_error_rate"],
        report["llm_cost_micro_usd"],
    ) == (
        {"by_draft_status": [], "by_reason_code": []},
        {"ticket_count": 0},
        {"suggestion_count": 0, "failed_count": 0},
        {"total": 0, "llm_call_count": 0},
    )


async def test_end_to_end_latency_measures_the_first_draft_of_each_ticket_with_percentiles(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.ticket_with_first_draft(START_AT - milliseconds(1_000), milliseconds(1_000))
    await rows.ticket_with_first_draft(START_AT + HOUR, milliseconds(2_000))
    await rows.ticket_with_first_draft(START_AT + 2 * HOUR, milliseconds(3_000))
    await rows.ticket_with_first_draft(START_AT + 4 * HOUR, milliseconds(10_001))
    retried = await rows.ticket_with_first_draft(START_AT + 3 * HOUR, milliseconds(4_000))
    await rows.suggestion(retried, retry_of(rows, START_AT + 3 * HOUR + MINUTE))
    early = await rows.ticket_with_first_draft(BEFORE_START, MINUTE)
    await rows.suggestion(early, retry_of(rows, START_AT))
    await rows.ticket_with_first_draft(END_AT - MINUTE, MINUTE)

    report = await load_report(backend, manager_headers)

    # percentile_cont over [1000, 2000, 3000, 4000, 10001]: the median is 3000, and the 95th
    # percentile is 4000 + 0.8 * 6001 = 8800.8, rounded to 8801.
    assert report["end_to_end_latency"] == {"ticket_count": 5, "p50_ms": 3_000, "p95_ms": 8_801}


async def test_end_to_end_latency_rounds_a_median_of_half_a_millisecond_up(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.ticket_with_first_draft(START_AT, milliseconds(1_000))
    await rows.ticket_with_first_draft(START_AT + HOUR, milliseconds(2_001))

    report = await load_report(backend, manager_headers)

    # percentile_cont over [1000, 2001]: the median is 1500.5, rounded half up to 1501, where
    # rounding half to even would give 1500; the 95th percentile is 1950.95, rounded to 1951.
    assert report["end_to_end_latency"] == {"ticket_count": 2, "p50_ms": 1_501, "p95_ms": 1_951}


async def test_end_to_end_latency_leaves_out_a_ticket_whose_first_draft_was_cancelled(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.ticket_with_first_draft(START_AT, milliseconds(1_000))
    await insert_ticket_whose_first_draft_was_cancelled(rows, START_AT + HOUR)

    report = await load_report(backend, manager_headers)

    assert report["end_to_end_latency"] == {"ticket_count": 1, "p50_ms": 1_000, "p95_ms": 1_000}


async def test_end_to_end_latency_counts_a_first_draft_that_ended_unavailable(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    unavailable = completed("unavailable", START_AT + milliseconds(2_000), AI_SERVICE_UNAVAILABLE)
    await rows.ticket_with_first_suggestion(START_AT, unavailable, unavailable)
    await rows.ticket_with_first_suggestion(
        START_AT + HOUR,
        completed("ready", START_AT + HOUR + milliseconds(500)),
        completed("llm_unavailable", START_AT + HOUR + milliseconds(4_000), "llm_unavailable"),
    )

    report = await load_report(backend, manager_headers)

    # percentile_cont over [2000, 4000]: the median is 3000, and the 95th percentile is
    # 2000 + 0.95 * 2000 = 3900.
    assert report["end_to_end_latency"] == {"ticket_count": 2, "p50_ms": 3_000, "p95_ms": 3_900}


async def test_end_to_end_latency_never_counts_the_draft_that_replaced_a_cancelled_one(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.ticket_with_first_draft(START_AT, milliseconds(1_000))
    corrected = await insert_ticket_whose_first_draft_was_cancelled(rows, START_AT + HOUR)
    corrected_at = START_AT + HOUR + MINUTE
    override = SuggestionSpec(
        created_at=corrected_at,
        trigger="intent_override",
        intent_override="refund_status",
        requested_by_account_id=rows.staff_account_id,
        analysis=completed("ready", corrected_at + milliseconds(250)),
        draft=completed("draft_ready", corrected_at + milliseconds(9_000)),
    )
    await rows.suggestion(corrected, override)

    report = await load_report(backend, manager_headers)

    assert report["end_to_end_latency"] == {"ticket_count": 1, "p50_ms": 1_000, "p95_ms": 1_000}


async def test_ai_error_rate_counts_completed_suggestions_without_cancelled_ones(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    ticket_id = await rows.ticket(imported_ticket(created_at=BEFORE_START))
    await rows.suggestions(
        ticket_id,
        suggestion_of(completed("ready", START_AT - MINUTE), completed("draft_ready", START_AT)),
        both_unavailable(START_AT + HOUR),
        suggestion_of(
            completed("ready", START_AT + 2 * HOUR),
            completed("llm_unavailable", START_AT + 2 * HOUR + MINUTE, "llm_unavailable"),
        ),
        suggestion_of(
            completed("ready", START_AT + 3 * HOUR), completed("cancelled", START_AT + 3 * HOUR)
        ),
        suggestion_of(completed("ready", START_AT + 4 * HOUR), SuggestionPartSpec()),
        suggestion_of(completed("ready", END_AT - MINUTE), completed("draft_ready", END_AT)),
        # Completed when its last part is: inside the period, although its first part is not.
        suggestion_of(
            completed("unavailable", BEFORE_START, AI_SERVICE_UNAVAILABLE),
            completed("draft_ready", START_AT + 5 * HOUR),
        ),
    )

    report = await load_report(backend, manager_headers)

    assert report["ai_error_rate"] == {"suggestion_count": 4, "failed_count": 3, "share": 0.75}


async def test_llm_cost_sums_the_draft_calls_of_the_period_and_rounds_the_average(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    ticket_id = await rows.ticket(imported_ticket(created_at=BEFORE_START))
    await rows.suggestions(
        ticket_id,
        with_ready_analysis(SuggestionPartSpec("draft_ready", START_AT, (), 300)),
        with_ready_analysis(SuggestionPartSpec("draft_ready", START_AT + HOUR, (), 121)),
        with_ready_analysis(completed("abstained", START_AT + 2 * HOUR)),
        with_ready_analysis(SuggestionPartSpec("draft_ready", END_AT, (), 1_000)),
    )

    report = await load_report(backend, manager_headers)

    assert report["llm_cost_micro_usd"] == {"total": 421, "llm_call_count": 2, "average": 211}
