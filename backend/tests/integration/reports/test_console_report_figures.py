"""The ticket figures of `getConsoleReport` on fixed records with known answers, against PostgreSQL.

Tickets created and closed, draft decisions, escalations, and handling time; the AI figures are
in `test_console_report_ai_figures`. The period is [2026-11-02, 2026-11-09). For each figure, one
test inserts records on both sides of the bounds of the period: one at exactly `start_at`, which
counts, and one at exactly `end_at`, which does not. Any other test checks one rule (backend
ticket workflow design, Reports and Testing).
"""

from datetime import timedelta

import pytest

from tests.integration.application import RunningBackend
from tests.integration.reports.report_rows import (
    BEFORE_START,
    DAY,
    END_AT,
    HOUR,
    MINUTE,
    ONE_MICROSECOND,
    START_AT,
    DecisionRowSpec,
    EscalationRowSpec,
    ReportRows,
    closed_after,
    imported_ticket,
    load_report,
)

pytestmark = pytest.mark.anyio


async def test_ticket_counts_count_creations_and_closings_of_the_period_by_mode(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.tickets(
        imported_ticket(created_at=START_AT),
        imported_ticket(created_at=END_AT - ONE_MICROSECOND, handling_mode="manual"),
        imported_ticket(created_at=END_AT),
        imported_ticket(created_at=BEFORE_START, status="closed", closed_at=START_AT + HOUR),
        imported_ticket(
            created_at=BEFORE_START, handling_mode="manual", status="closed", closed_at=END_AT
        ),
        imported_ticket(
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
    ticket_id = await rows.ticket(imported_ticket(created_at=BEFORE_START))
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


async def test_handling_time_is_the_median_from_first_view_to_reply_per_mode(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.tickets(
        closed_after("assisted", START_AT, 10 * MINUTE),
        closed_after("assisted", START_AT + 2 * DAY, 25 * MINUTE),
        closed_after("manual", START_AT + 3 * DAY, 2 * MINUTE),
        closed_after("manual", END_AT, 5 * MINUTE),
        imported_ticket(created_at=BEFORE_START, status="closed", closed_at=START_AT + DAY),
    )

    report = await load_report(backend, manager_headers)

    assert report["handling_time"] == {
        "assisted": {"ticket_count": 2, "p50_ms": 1_050_000},
        "manual": {"ticket_count": 1, "p50_ms": 120_000},
    }


async def test_handling_time_counts_only_tickets_first_viewed_no_later_than_their_reply(
    backend: RunningBackend, rows: ReportRows, manager_headers: dict[str, str]
) -> None:
    await rows.tickets(
        # Closed at 10:00 and first viewed at 11:00, for example by a manager who opened it.
        imported_ticket(
            created_at=START_AT + 9 * HOUR,
            status="closed",
            handling_started_at=START_AT + 11 * HOUR,
            closed_at=START_AT + 10 * HOUR,
        ),
        # First viewed at the moment of the reply: a handling time of 0 ms, which counts.
        closed_after("manual", START_AT + DAY, timedelta(0)),
    )

    report = await load_report(backend, manager_headers)

    assert report["handling_time"] == {
        "assisted": {"ticket_count": 0},
        "manual": {"ticket_count": 1, "p50_ms": 0},
    }
