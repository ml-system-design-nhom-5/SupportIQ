"""Adapter tests of `PostgresDecisionRecordSource` against PostgreSQL 17 (TEST-01).

backend writes every JSON value that the export reads, so a value of another shape is a defect of
backend, read as an unexpected failure (ERR-05). The defect is stored as the owner after valid
rows; a final suggestion part never changes, so the part that holds it stays pending.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform import UnexpectedFailureError
from app.platform.adapters.database import create_session_factory
from app.reports import DecisionRecord
from app.reports.adapters.decision_records import PostgresDecisionRecordSource
from app.tickets import StaffReasonCode
from tests.integration.builders import DatabaseBuilder, SuggestionSpec
from tests.integration.reports.report_rows import (
    HOUR,
    REPORT_PERIOD,
    START_AT,
    DecisionRowSpec,
    ReportRows,
    imported_ticket,
)

pytestmark = pytest.mark.anyio

# A part result that is not a JSON object, and staff reason codes that are not a JSON array.
WRONG_SHAPES = [
    """UPDATE suggestion_parts SET result = '["not", "an", "object"]' WHERE part = 'draft'""",
    """UPDATE staff_decisions SET staff_reason_codes = '{"kb_gap": 1}'""",
]
WRONG_SHAPE_IDS = ["part-result", "decision-reason-codes"]


async def load_records(engine: AsyncEngine) -> tuple[DecisionRecord, ...]:
    async with create_session_factory(engine)() as session:
        return await PostgresDecisionRecordSource(session).load_decision_records(REPORT_PERIOD)


async def insert_closed_ticket(rows: ReportRows) -> None:
    closed_at = START_AT + HOUR
    ticket_id = await rows.ticket(
        imported_ticket(created_at=START_AT, status="closed", closed_at=closed_at)
    )
    await rows.suggestion(ticket_id, SuggestionSpec(created_at=START_AT))
    await rows.decision(ticket_id, DecisionRowSpec("reject", closed_at, ("kb_gap",)))


async def test_load_decision_records_reads_the_valid_rows_that_the_defects_change(
    app_engine: AsyncEngine, rows: ReportRows
) -> None:
    await insert_closed_ticket(rows)

    (record,) = await load_records(app_engine)

    assert record.suggestion is not None
    assert (record.suggestion.draft.result_fields, record.decisions[0].staff_reason_codes) == (
        None,
        (StaffReasonCode.KB_GAP,),
    )


@pytest.mark.parametrize("wrong_shape", WRONG_SHAPES, ids=WRONG_SHAPE_IDS)
async def test_load_decision_records_of_a_stored_value_of_the_wrong_shape_is_an_unexpected_failure(
    app_engine: AsyncEngine, builder: DatabaseBuilder, rows: ReportRows, wrong_shape: str
) -> None:
    await insert_closed_ticket(rows)
    await builder.execute(text(wrong_shape))

    with pytest.raises(UnexpectedFailureError):
        await load_records(app_engine)
