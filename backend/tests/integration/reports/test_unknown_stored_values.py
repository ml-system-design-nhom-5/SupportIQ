"""Adapter tests of the report and the export on reason codes that no enum has (PY-20).

backend writes every reason code that the report and the export read, so a code that no member
of its enum has is a defect of backend: each source reads it as an unexpected failure whose
cause is the `ValueError` (ERR-05). A reason code is a value of a JSON array, which no check
constraint lists, so the rows hold one as they are inserted.
"""

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform import UnexpectedFailureError
from app.platform.adapters.database import create_session_factory
from app.reports.adapters.ai_figures import PostgresAiFigures
from app.reports.adapters.decision_records import PostgresDecisionRecordSource
from app.reports.adapters.ticket_figures import PostgresTicketFigures
from app.reports.domain import HandlingTime, TicketCounts
from app.tickets.adapters.tables import TicketRow
from tests.integration.database import WorkerDatabase
from tests.integration.reports.report_rows import (
    HOUR,
    MINUTE,
    REPORT_PERIOD,
    START_AT,
    DecisionRowSpec,
    EscalationRowSpec,
    ReportRows,
    closed_after,
    completed,
    imported_ticket,
)
from tests.integration.stored_values import (
    DROP_HANDLING_MODE_CHECK,
    UNKNOWN_VALUE,
    session_without_check,
)

pytestmark = pytest.mark.anyio

type ReadTicketFigures = Callable[[PostgresTicketFigures], Awaitable[TicketCounts | HandlingTime]]


async def load_ticket_counts(figures: PostgresTicketFigures) -> TicketCounts:
    return await figures.load_ticket_counts(REPORT_PERIOD)


async def load_handling_time(figures: PostgresTicketFigures) -> HandlingTime:
    return await figures.load_handling_time(REPORT_PERIOD)


@pytest.mark.parametrize(
    "read_figures", [load_ticket_counts, load_handling_time], ids=["ticket-counts", "handling-time"]
)
async def test_reading_tickets_of_an_unknown_handling_mode_is_an_unexpected_failure(
    worker_database: WorkerDatabase, rows: ReportRows, read_figures: ReadTicketFigures
) -> None:
    ticket_id = await rows.ticket(closed_after("assisted", START_AT + HOUR, MINUTE))
    unknown_mode = (
        update(TicketRow)
        .where(TicketRow.ticket_id == ticket_id)
        .values(handling_mode=UNKNOWN_VALUE)
    )

    async with session_without_check(
        worker_database, DROP_HANDLING_MODE_CHECK, unknown_mode
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await read_figures(PostgresTicketFigures(session))

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_draft_decisions_of_an_unknown_staff_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, rows: ReportRows
) -> None:
    closed_at = START_AT + HOUR
    ticket_id = await rows.ticket(
        imported_ticket(created_at=START_AT, status="closed", closed_at=closed_at)
    )
    await rows.decision(ticket_id, DecisionRowSpec("reject", closed_at, (UNKNOWN_VALUE,)))

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresTicketFigures(session).load_draft_decisions(REPORT_PERIOD)

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_ai_outcomes_of_an_unknown_ai_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, rows: ReportRows
) -> None:
    await rows.ticket_with_first_suggestion(
        START_AT,
        completed("ready", START_AT + HOUR),
        completed("abstained", START_AT + HOUR, UNKNOWN_VALUE),
    )

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresAiFigures(session).load_ai_outcomes(REPORT_PERIOD)

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_escalations_of_an_unknown_staff_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, rows: ReportRows
) -> None:
    await rows.escalated_tickets(EscalationRowSpec(START_AT + HOUR, (UNKNOWN_VALUE,)))

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresTicketFigures(session).load_escalations(REPORT_PERIOD)

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_decision_records_of_an_unknown_staff_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, rows: ReportRows
) -> None:
    closed_at = START_AT + HOUR
    ticket_id = await rows.ticket(
        imported_ticket(created_at=START_AT, status="closed", closed_at=closed_at)
    )
    await rows.decision(ticket_id, DecisionRowSpec("reject", closed_at, (UNKNOWN_VALUE,)))

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresDecisionRecordSource(session).load_decision_records(REPORT_PERIOD)

    assert isinstance(caught.value.__cause__, ValueError)
