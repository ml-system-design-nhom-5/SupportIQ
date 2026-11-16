"""Guardrail: the decision-record export holds pseudonymized text only (TEST-26, SEC-33).

The export may carry the pseudonymized message and the AI text as `ai-service` received and
sent them, never a value that a person can read back: no customer message as written, no reply
body or staff note, which hold restored values, no staff note of the AI, and no value of the
pseudonym map (SEC-33, SEC-37). The scenario marks each of them with a unique text.
"""

from pathlib import Path

import pytest

from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.reports.export_scenario import (
    AI_STAFF_NOTE,
    ESCALATION_NOTE,
    MAP_VALUE,
    OUTPUT,
    PSEUDONYMIZED_MESSAGE,
    RAW_MESSAGE,
    REPLY_BODY,
    REPLY_NOTE,
    insert_export_scenario,
    run_export,
)
from tests.integration.reports.report_rows import ReportRows

pytestmark = pytest.mark.anyio


async def test_the_export_holds_no_text_that_a_person_can_read_back(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, tmp_path: Path
) -> None:
    staff_account_id = await builder.account(AccountSpec("staff"))
    tickets = await insert_export_scenario(ReportRows(builder, staff_account_id))

    await run_export(worker_database, tmp_path)

    text = (tmp_path / OUTPUT).read_text(encoding="utf-8")
    readable = (RAW_MESSAGE, MAP_VALUE, REPLY_BODY, REPLY_NOTE, ESCALATION_NOTE, AI_STAFF_NOTE)
    assert tickets.closed in text
    assert PSEUDONYMIZED_MESSAGE in text
    assert [value for value in readable if value in text] == []
