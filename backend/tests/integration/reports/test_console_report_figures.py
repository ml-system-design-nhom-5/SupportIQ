"""Every figure of `getConsoleReport` on fixed records with known answers, against PostgreSQL.

The period is [2026-11-02, 2026-11-09). Each test inserts records on both sides of its bounds,
a record at exactly `start_at`, which counts, and one at exactly `end_at`, which does not
(backend ticket workflow design, Reports and Testing).
"""

from datetime import timedelta
from http import HTTPStatus

import pytest

from tests.integration.application import RunningBackend
from tests.integration.reports.report_rows import (
    BEFORE_START,
    CONSOLE_REPORTS,
    END_AT,
    ONE_MICROSECOND,
    PERIOD,
    START_AT,
    DecisionRowSpec,
    EscalationRowSpec,
    PartRowSpec,
    ReportRows,
    ReportTicketSpec,
    SuggestionRowSpec,
    closed_after,
    completed,
)

pytestmark = pytest.mark.anyio

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
MINUTE = timedelta(minutes=1)


def milliseconds(count: int) -> timedelta:
    return timedelta(milliseconds=count)


async def load_report(backend: RunningBackend, headers: dict[str, str]) -> dict[str, object]:
    response = await backend.client.get(CONSOLE_REPORTS, params=PERIOD, headers=headers)
    assert response.status_code == HTTPStatus.OK
    return response.json()


async def test_ticket_counts_count_creations_and_closings_of_the_period_by_mode(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.tickets(
        ReportTicketSpec(created_at=START_AT),
        ReportTicketSpec(created_at=END_AT - ONE_MICROSECOND, handling_mode="manual"),
        ReportTicketSpec(created_at=END_AT),
        ReportTicketSpec(created_at=BEFORE_START, status="closed", closed_at=START_AT + HOUR),
        ReportTicketSpec(
            created_at=BEFORE_START, handling_mode="manual", status="closed", closed_at=END_AT
        ),
        ReportTicketSpec(
            created_at=START_AT + DAY,
            handling_mode="manual",
            status="closed",
            closed_at=START_AT + 2 * DAY,
        ),
    )

    report = await load_report(backend, manager_headers)

    assert report["ticket_counts"] == {
        "created": {"assisted_count": 1, "manual_count": 2},
        "closed": {"assisted_count": 1, "manual_count": 1},
    }


async def test_draft_decisions_count_each_reason_of_an_edit_and_leave_out_escalations(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    ticket_id = await rows.ticket(ReportTicketSpec(created_at=BEFORE_START))
    await rows.decisions(
        ticket_id,
        DecisionRowSpec("approve", START_AT),
        DecisionRowSpec("edit", START_AT + HOUR, ("tone_or_clarity", "wrong_source")),
        DecisionRowSpec("edit", START_AT + 2 * HOUR),
        DecisionRowSpec("reject", START_AT + 3 * HOUR, ("kb_gap",)),
        DecisionRowSpec("escalate", START_AT + 4 * HOUR, ("other",)),
        DecisionRowSpec("approve", END_AT),
        DecisionRowSpec("reject", BEFORE_START, ("wrong_intent",)),
    )

    report = await load_report(backend, manager_headers)

    assert report["draft_decisions"] == {
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


async def test_escalations_count_once_in_the_total_and_once_under_each_reason(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.escalated_tickets(
        EscalationRowSpec(START_AT, ("other", "case_exception")),
        EscalationRowSpec(END_AT - ONE_MICROSECOND, ("case_exception",)),
        EscalationRowSpec(END_AT, ("kb_gap",)),
        EscalationRowSpec(BEFORE_START, ("kb_gap",)),
    )

    report = await load_report(backend, manager_headers)

    assert report["escalations"] == {
        "escalation_count": 2,
        "by_reason": [
            {"staff_reason_code": "case_exception", "escalation_count": 2},
            {"staff_reason_code": "other", "escalation_count": 1},
        ],
    }


async def test_ai_outcomes_count_completed_drafts_by_status_and_code_without_cancelled_ones(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    ticket_id = await rows.ticket(ReportTicketSpec(created_at=BEFORE_START))
    await rows.suggestions(
        ticket_id,
        SuggestionRowSpec(BEFORE_START, draft=completed("draft_ready", START_AT)),
        SuggestionRowSpec(
            BEFORE_START, draft=completed("abstained", START_AT + HOUR, "low_confidence")
        ),
        SuggestionRowSpec(
            BEFORE_START,
            draft=completed(
                "escalation_recommended",
                START_AT + 2 * HOUR,
                "requires_authority",
                "human_agent_requested",
            ),
        ),
        SuggestionRowSpec(
            BEFORE_START,
            draft=completed("unavailable", START_AT + 3 * HOUR, "ai_service_unavailable"),
        ),
        # A reason code on a cancelled part, so the test proves that the query leaves it out.
        SuggestionRowSpec(
            BEFORE_START, draft=completed("cancelled", START_AT + 4 * HOUR, "budget_exceeded")
        ),
        SuggestionRowSpec(BEFORE_START, draft=completed("draft_ready", END_AT)),
        SuggestionRowSpec(BEFORE_START, draft=PartRowSpec()),
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


async def test_end_to_end_latency_measures_the_first_draft_of_each_ticket_with_percentiles(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.ticket_with_first_draft(START_AT, milliseconds(1_000))
    await rows.ticket_with_first_draft(START_AT + HOUR, milliseconds(2_000))
    await rows.ticket_with_first_draft(START_AT + 2 * HOUR, milliseconds(3_000))
    await rows.ticket_with_first_draft(START_AT + 4 * HOUR, milliseconds(10_001))
    retried = await rows.ticket_with_first_draft(START_AT + 3 * HOUR, milliseconds(4_000))
    retry = SuggestionRowSpec(
        START_AT + 3 * HOUR + MINUTE,
        draft=completed("draft_ready", START_AT + 3 * HOUR + 2 * MINUTE),
        is_retry=True,
    )
    await rows.suggestion(retried, retry)
    early = await rows.ticket_with_first_draft(BEFORE_START, MINUTE)
    late_retry = SuggestionRowSpec(
        START_AT, draft=completed("draft_ready", START_AT + MINUTE), is_retry=True
    )
    await rows.suggestion(early, late_retry)
    await rows.ticket_with_first_draft(END_AT - MINUTE, MINUTE)

    report = await load_report(backend, manager_headers)

    # percentile_cont over [1000, 2000, 3000, 4000, 10001]: the median is 3000, and the 95th
    # percentile is 4000 + 0.8 * 6001 = 8800.8, rounded to 8801.
    assert report["end_to_end_latency"] == {"ticket_count": 5, "p50_ms": 3_000, "p95_ms": 8_801}


async def test_end_to_end_latency_leaves_out_a_ticket_whose_first_draft_was_cancelled(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.ticket_with_first_draft(START_AT, milliseconds(1_000))
    cancelled = await rows.ticket(ReportTicketSpec(created_at=START_AT + HOUR))
    first = SuggestionRowSpec(
        START_AT + HOUR, draft=completed("cancelled", START_AT + HOUR + milliseconds(500))
    )
    await rows.suggestion(cancelled, first)

    report = await load_report(backend, manager_headers)

    assert report["end_to_end_latency"] == {"ticket_count": 1, "p50_ms": 1_000, "p95_ms": 1_000}


async def test_end_to_end_latency_counts_a_first_draft_that_ended_unavailable(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    for offset, status, latency_ms in (
        (0, "unavailable", 2_000),
        (1, "llm_unavailable", 4_000),
    ):
        created_at = START_AT + offset * HOUR
        ticket_id = await rows.ticket(ReportTicketSpec(created_at=created_at))
        draft = completed(status, created_at + milliseconds(latency_ms))
        await rows.suggestion(ticket_id, SuggestionRowSpec(created_at, draft=draft))

    report = await load_report(backend, manager_headers)

    # percentile_cont over [2000, 4000]: the median is 3000, and the 95th percentile is
    # 2000 + 0.95 * 2000 = 3900.
    assert report["end_to_end_latency"] == {"ticket_count": 2, "p50_ms": 3_000, "p95_ms": 3_900}


async def test_end_to_end_latency_never_counts_the_draft_that_replaced_a_cancelled_one(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.ticket_with_first_draft(START_AT, milliseconds(1_000))
    corrected = await rows.ticket(ReportTicketSpec(created_at=START_AT + HOUR))
    await rows.suggestions(
        corrected,
        SuggestionRowSpec(
            START_AT + HOUR, draft=completed("cancelled", START_AT + HOUR + milliseconds(500))
        ),
        SuggestionRowSpec(
            START_AT + HOUR + MINUTE,
            draft=completed("draft_ready", START_AT + HOUR + MINUTE + milliseconds(9_000)),
            intent_override="refund_status",
        ),
    )

    report = await load_report(backend, manager_headers)

    assert report["end_to_end_latency"] == {"ticket_count": 1, "p50_ms": 1_000, "p95_ms": 1_000}


async def test_ai_error_rate_counts_completed_suggestions_without_cancelled_ones(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    ticket_id = await rows.ticket(ReportTicketSpec(created_at=BEFORE_START))
    unavailable = "ai_service_unavailable"
    await rows.suggestions(
        ticket_id,
        SuggestionRowSpec(
            BEFORE_START,
            analysis=completed("ready", START_AT),
            draft=completed("draft_ready", START_AT + MINUTE),
        ),
        SuggestionRowSpec(
            BEFORE_START,
            analysis=completed("unavailable", START_AT + HOUR, unavailable),
            draft=completed("unavailable", START_AT + HOUR, unavailable),
        ),
        SuggestionRowSpec(
            BEFORE_START,
            analysis=completed("ready", START_AT + 2 * HOUR),
            draft=completed("llm_unavailable", START_AT + 2 * HOUR + MINUTE, "llm_unavailable"),
        ),
        SuggestionRowSpec(
            BEFORE_START,
            analysis=completed("ready", START_AT + 3 * HOUR),
            draft=completed("cancelled", START_AT + 3 * HOUR),
        ),
        SuggestionRowSpec(BEFORE_START, analysis=completed("ready", START_AT + 4 * HOUR)),
        SuggestionRowSpec(
            BEFORE_START,
            analysis=completed("ready", END_AT - MINUTE),
            draft=completed("draft_ready", END_AT),
        ),
        SuggestionRowSpec(
            BEFORE_START,
            analysis=completed("unavailable", BEFORE_START, unavailable),
            draft=completed("draft_ready", START_AT + 5 * HOUR),
        ),
    )

    report = await load_report(backend, manager_headers)

    assert report["ai_error_rate"] == {"suggestion_count": 4, "failed_count": 3, "share": 0.75}


async def test_llm_cost_sums_the_draft_calls_of_the_period_and_rounds_the_average(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    ticket_id = await rows.ticket(ReportTicketSpec(created_at=BEFORE_START))
    await rows.suggestions(
        ticket_id,
        SuggestionRowSpec(BEFORE_START, draft=PartRowSpec("draft_ready", START_AT, (), 300)),
        SuggestionRowSpec(BEFORE_START, draft=PartRowSpec("draft_ready", START_AT + HOUR, (), 121)),
        SuggestionRowSpec(BEFORE_START, draft=completed("abstained", START_AT + 2 * HOUR)),
        SuggestionRowSpec(BEFORE_START, draft=PartRowSpec("draft_ready", END_AT, (), 1_000)),
    )

    report = await load_report(backend, manager_headers)

    assert report["llm_cost_micro_usd"] == {"total": 421, "llm_call_count": 2, "average": 211}


async def test_handling_time_is_the_median_from_first_view_to_reply_per_mode(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.tickets(
        closed_after("assisted", START_AT + DAY, timedelta(minutes=10)),
        closed_after("assisted", START_AT + 2 * DAY, timedelta(minutes=25)),
        closed_after("manual", START_AT + 3 * DAY, timedelta(minutes=2)),
        closed_after("manual", END_AT, timedelta(minutes=5)),
        ReportTicketSpec(created_at=BEFORE_START, status="closed", closed_at=START_AT + DAY),
    )

    report = await load_report(backend, manager_headers)

    assert report["handling_time"] == {
        "assisted": {"ticket_count": 2, "p50_ms": 1_050_000},
        "manual": {"ticket_count": 1, "p50_ms": 120_000},
    }
