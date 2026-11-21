"""The decision-record export with fakes: read in one transaction, then write (SEC-33)."""

import pytest

from app.platform import DatabaseUnavailableError, EventName
from app.reports import ExportWriteFailedError
from tests.unit.reports.fakes import (
    PERIOD,
    RECORD,
    RecordingDecisionRecordFile,
    build_export_harness,
)

pytestmark = pytest.mark.anyio


async def test_export_writes_the_records_of_the_period() -> None:
    harness = build_export_harness()

    await harness.use_case.execute(PERIOD)

    assert harness.source.periods == [PERIOD]
    assert harness.destination.saved == [(RECORD,)]


async def test_export_reads_without_committing_and_records_the_export() -> None:
    harness = build_export_harness()

    await harness.use_case.execute(PERIOD)

    assert (harness.transactions.commit_count, harness.transactions.rollback_count) == (0, 1)
    assert harness.events.names() == (EventName.DECISIONS_EXPORTED,)


async def test_export_without_the_database_writes_nothing() -> None:
    harness = build_export_harness(begin_failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await harness.use_case.execute(PERIOD)

    assert harness.destination.saved == []
    assert harness.events.names() == ()


async def test_export_whose_read_fails_in_the_transaction_rolls_back_and_writes_nothing() -> None:
    harness = build_export_harness(load_failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await harness.use_case.execute(PERIOD)

    assert (harness.transactions.commit_count, harness.transactions.rollback_count) == (0, 1)
    assert harness.destination.saved == []
    assert harness.events.names() == ()


async def test_export_whose_file_cannot_be_written_records_no_export() -> None:
    destination = RecordingDecisionRecordFile(failure=ExportWriteFailedError())
    harness = build_export_harness(destination=destination)

    with pytest.raises(ExportWriteFailedError):
        await harness.use_case.execute(PERIOD)

    assert harness.events.names() == ()
