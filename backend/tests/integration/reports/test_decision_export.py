"""The decision-record export of the shared scenario against PostgreSQL, into `exports/` (SEC-33).

Each test exports the records of `export_scenario` as `supportiq_app` and reads the file back.
"""

import json
from pathlib import Path

import pytest

from supportiq_backend.platform import EventName
from tests.integration.database import WorkerDatabase
from tests.integration.reports.export_scenario import (
    OUTPUT,
    PSEUDONYMIZED_MESSAGE,
    STUDY_BATCH,
    STUDY_PAIR_ID,
    ExportTickets,
    exported_analysis,
    insert_export_scenario,
    read_records,
    run_export,
)
from tests.integration.reports.report_rows import ReportRows
from tests.integration.tickets.console_requests import (
    PREDICTED_INTENT,
    asset_versions,
    draft_ready_outcome,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
async def tickets(rows: ReportRows) -> ExportTickets:
    return await insert_export_scenario(rows)


async def test_export_writes_one_line_per_ticket_closed_or_escalated_in_the_period(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    await run_export(worker_database, tmp_path)

    lines = (tmp_path / OUTPUT).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["ticket_id"] for line in lines] == [
        tickets.closed,
        tickets.escalated,
        tickets.manual,
        tickets.failed,
    ]


async def test_export_records_a_closed_ticket_with_its_pseudonymized_exchange_and_decision(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    await run_export(worker_database, tmp_path)

    assert read_records(tmp_path)[tickets.closed] == {
        "ticket_id": tickets.closed,
        "handling_mode": "assisted",
        "study_pair_id": STUDY_PAIR_ID,
        "study_batch": STUDY_BATCH,
        "created_at": "2026-11-02T01:00:00Z",
        "handling_started_at": "2026-11-02T02:00:00Z",
        "closed_at": "2026-11-02T03:00:00Z",
        "handling_time_ms": 3_600_000,
        "suggestion": {
            "suggestion_id": str(tickets.closed_suggestion_id),
            "trigger": "ticket_created",
            "created_at": "2026-11-02T01:00:00Z",
            "pseudonymized_message": PSEUDONYMIZED_MESSAGE,
            "analysis": {
                "status": "ready",
                "reason_codes": [],
                "completed_at": "2026-11-02T01:00:01Z",
                "result": exported_analysis(),
            },
            "draft": {
                "status": "draft_ready",
                "reason_codes": [],
                "completed_at": "2026-11-02T01:00:03Z",
                "result": {"draft": draft_ready_outcome()["draft"], "versions": asset_versions()},
            },
        },
        "decisions": [
            {
                "decision_type": "approve",
                "staff_reason_codes": [],
                "change_ratio": 0,
                "final_intent": PREDICTED_INTENT,
                "decided_at": "2026-11-02T03:00:00Z",
            }
        ],
    }


async def test_export_records_an_escalated_ticket_without_a_draft_or_a_handling_time(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    await run_export(worker_database, tmp_path)

    assert read_records(tmp_path)[tickets.escalated] == {
        "ticket_id": tickets.escalated,
        "handling_mode": "assisted",
        "created_at": "2026-11-02T04:00:00Z",
        "handling_started_at": "2026-11-02T05:00:00Z",
        "escalated_at": "2026-11-02T06:00:00Z",
        "suggestion": {
            "suggestion_id": str(tickets.escalated_suggestion_id),
            "trigger": "ticket_created",
            "created_at": "2026-11-02T04:00:00Z",
            "pseudonymized_message": PSEUDONYMIZED_MESSAGE,
            "analysis": {
                "status": "ready",
                "reason_codes": [],
                "completed_at": "2026-11-02T04:00:01Z",
                "result": exported_analysis(),
            },
            "draft": {
                "status": "escalation_recommended",
                "reason_codes": ["human_agent_requested"],
                "completed_at": "2026-11-02T04:00:03Z",
                "result": {"versions": asset_versions()},
            },
        },
        "decisions": [
            {
                "decision_type": "escalate",
                "staff_reason_codes": ["case_exception"],
                "final_intent": PREDICTED_INTENT,
                "decided_at": "2026-11-02T06:00:00Z",
            }
        ],
    }


async def test_export_records_a_manual_ticket_without_any_text(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    await run_export(worker_database, tmp_path)

    assert read_records(tmp_path)[tickets.manual] == {
        "ticket_id": tickets.manual,
        "handling_mode": "manual",
        "created_at": "2026-11-02T06:00:00Z",
        "handling_started_at": "2026-11-02T06:00:00Z",
        "closed_at": "2026-11-02T07:00:00Z",
        "handling_time_ms": 3_600_000,
        "decisions": [],
    }


async def test_export_records_a_failed_pseudonymization_without_any_text(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    await run_export(worker_database, tmp_path)

    suggestion = read_records(tmp_path)[tickets.failed]["suggestion"]
    failed_part = {
        "status": "unavailable",
        "reason_codes": ["pseudonymization_failed"],
        "completed_at": "2026-11-02T07:00:01Z",
    }
    assert suggestion == {
        "suggestion_id": str(tickets.failed_suggestion_id),
        "trigger": "ticket_created",
        "created_at": "2026-11-02T07:00:00Z",
        "analysis": failed_part,
        "draft": failed_part,
    }


async def test_export_records_that_it_wrote_the_file(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    events = await run_export(worker_database, tmp_path)

    assert tickets.closed in read_records(tmp_path)
    assert events.names() == (EventName.DECISIONS_EXPORTED,)


async def test_export_of_a_period_without_records_writes_an_empty_file(
    worker_database: WorkerDatabase, tmp_path: Path
) -> None:
    await run_export(worker_database, tmp_path)

    assert (tmp_path / OUTPUT).read_text(encoding="utf-8") == ""


async def test_export_creates_the_folders_of_its_path_inside_exports(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    output = Path("exports/2026-11/week-45/../decisions.jsonl")

    await run_export(worker_database, tmp_path, output)

    lines = (tmp_path / "exports/2026-11/decisions.jsonl").read_text(encoding="utf-8")
    assert tickets.closed in lines
