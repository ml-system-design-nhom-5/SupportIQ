"""The export record of one ticket beyond the shared scenario, against PostgreSQL (SEC-33).

A ticket first viewed after its reply, and a ticket with an intent override, an escalation, and a
manager's reply from a changed proposal (backend ticket workflow design, The decision-record
export).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from tests.integration.builders import SuggestionSpec
from tests.integration.database import WorkerDatabase
from tests.integration.reports.export_scenario import (
    PSEUDONYMIZED_MESSAGE,
    read_records,
    run_export,
    sent_request,
)
from tests.integration.reports.report_rows import (
    HOUR,
    MINUTE,
    SECOND,
    START_AT,
    DecisionRowSpec,
    ReportRows,
    completed,
    imported_ticket,
)
from tests.integration.tickets.console_requests import CORRECTED_INTENT

pytestmark = pytest.mark.anyio


@dataclass(frozen=True, slots=True)
class OverriddenTicket:
    """A ticket whose intent staff corrected, which they escalated, and a manager closed.

    Attributes:
        ticket_id: The ticket.
        suggestion_id: Its current suggestion, of the intent override.
    """

    ticket_id: str
    suggestion_id: UUID


async def insert_overridden_ticket(rows: ReportRows) -> OverriddenTicket:
    """Insert a ticket with an intent override, an escalation, and a reply from a changed proposal.

    Created at 09:00, first viewed at 10:00, its intent corrected a minute later, escalated at
    11:00, and replied to at 12:00. The suggestion of the correction supersedes the first one.
    """
    created_at = START_AT + 9 * HOUR
    ticket_id = await rows.ticket(
        imported_ticket(
            created_at=created_at,
            status="closed",
            handling_started_at=created_at + HOUR,
            closed_at=created_at + 3 * HOUR,
        )
    )
    first = SuggestionSpec(
        created_at=created_at,
        analysis=completed("ready", created_at + SECOND),
        draft=completed("draft_ready", created_at + SECOND),
    )
    overridden_at = created_at + HOUR + MINUTE
    override = SuggestionSpec(
        created_at=overridden_at,
        trigger="intent_override",
        intent_override=CORRECTED_INTENT,
        requested_by_account_id=rows.staff_account_id,
        request=sent_request(),
        analysis=completed("ready", overridden_at + SECOND),
        draft=completed("draft_ready", overridden_at + SECOND),
    )
    await rows.suggestion(ticket_id, first)
    ticket = OverriddenTicket(ticket_id, await rows.suggestion(ticket_id, override))
    await _insert_escalation_and_manager_reply(rows, ticket, created_at + 2 * HOUR)
    return ticket


async def _insert_escalation_and_manager_reply(
    rows: ReportRows, ticket: OverriddenTicket, escalated_at: datetime
) -> None:
    await rows.escalation(ticket.ticket_id, escalated_at, "case_exception")
    await rows.decisions(
        ticket.ticket_id,
        DecisionRowSpec(
            "escalate",
            escalated_at,
            ("case_exception",),
            suggestion_id=ticket.suggestion_id,
            final_intent=CORRECTED_INTENT,
        ),
        DecisionRowSpec(
            "edit",
            escalated_at + HOUR,
            ("tone_or_clarity",),
            suggestion_id=ticket.suggestion_id,
            change_ratio=0.25,
            final_intent=CORRECTED_INTENT,
            is_proposal_changed=True,
        ),
    )


@pytest.fixture
async def overridden(rows: ReportRows) -> OverriddenTicket:
    return await insert_overridden_ticket(rows)


async def test_export_records_a_ticket_first_viewed_after_its_reply_without_a_handling_time(
    worker_database: WorkerDatabase, tmp_path: Path, rows: ReportRows
) -> None:
    ticket_id = await rows.ticket(
        imported_ticket(
            created_at=START_AT + 9 * HOUR,
            status="closed",
            handling_started_at=START_AT + 11 * HOUR,
            closed_at=START_AT + 10 * HOUR,
        )
    )

    await run_export(worker_database, tmp_path)

    assert read_records(tmp_path)[ticket_id] == {
        "ticket_id": ticket_id,
        "handling_mode": "assisted",
        "created_at": "2026-11-02T09:00:00Z",
        "handling_started_at": "2026-11-02T11:00:00Z",
        "closed_at": "2026-11-02T10:00:00Z",
        "decisions": [],
    }


async def test_export_records_the_escalation_and_the_manager_reply_of_a_ticket_in_order(
    worker_database: WorkerDatabase, tmp_path: Path, overridden: OverriddenTicket
) -> None:
    await run_export(worker_database, tmp_path)

    record = read_records(tmp_path)[overridden.ticket_id]
    assert (record["escalated_at"], record["closed_at"], record["handling_time_ms"]) == (
        "2026-11-02T11:00:00Z",
        "2026-11-02T12:00:00Z",
        7_200_000,
    )
    assert record["decisions"] == [
        {
            "decision_type": "escalate",
            "staff_reason_codes": ["case_exception"],
            "final_intent": CORRECTED_INTENT,
            "decided_at": "2026-11-02T11:00:00Z",
        },
        {
            "decision_type": "edit",
            "staff_reason_codes": ["tone_or_clarity"],
            "change_ratio": 0.25,
            "final_intent": CORRECTED_INTENT,
            "is_proposal_changed": True,
            "decided_at": "2026-11-02T12:00:00Z",
        },
    ]


async def test_export_records_the_current_suggestion_of_an_intent_override(
    worker_database: WorkerDatabase, tmp_path: Path, overridden: OverriddenTicket
) -> None:
    await run_export(worker_database, tmp_path)

    assert read_records(tmp_path)[overridden.ticket_id]["suggestion"] == {
        "suggestion_id": str(overridden.suggestion_id),
        "trigger": "intent_override",
        "intent_override": CORRECTED_INTENT,
        "created_at": "2026-11-02T10:01:00Z",
        "pseudonymized_message": PSEUDONYMIZED_MESSAGE,
        "analysis": {
            "status": "ready",
            "reason_codes": [],
            "completed_at": "2026-11-02T10:01:01Z",
        },
        "draft": {
            "status": "draft_ready",
            "reason_codes": [],
            "completed_at": "2026-11-02T10:01:01Z",
        },
    }
