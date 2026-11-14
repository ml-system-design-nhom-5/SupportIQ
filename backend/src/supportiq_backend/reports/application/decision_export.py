"""`backend export-decisions`: the decision records of a period, written to `exports/` (SEC-33).

The command runs as `supportiq_app` and only reads. Its output path was checked before this use
case runs, so a refused path reads and writes nothing. The records are read in one transaction
and written only after it, so a database failure writes nothing either.
"""

from dataclasses import dataclass

from supportiq_backend.platform import EventName, EventRecorder, TransactionRunner
from supportiq_backend.reports.domain import DecisionRecordFile, DecisionRecordSource, ReportPeriod


@dataclass(frozen=True, slots=True)
class ExportStores:
    """The stores of the export, in one read transaction.

    Attributes:
        records: The decision records.
    """

    records: DecisionRecordSource


class ExportDecisions:
    """Write the decision records of one period to the export file."""

    def __init__(
        self,
        transactions: TransactionRunner[ExportStores],
        destination: DecisionRecordFile,
        events: EventRecorder,
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the read transaction.
            destination: The output file, already checked to be inside `exports/`.
            events: Where `decisions.exported` is recorded.
        """
        self._transactions = transactions
        self._destination = destination
        self._events = events

    async def execute(self, period: ReportPeriod) -> None:
        """Read the records of the period, then write them.

        Args:
            period: The period.

        Raises:
            DatabaseUnavailableError: The database is not available or a timeout fired.
            ExportWriteFailedError: The file could not be written.
        """
        async with self._transactions.begin() as transaction:
            records = await transaction.stores.records.load_decision_records(period)
        await self._destination.save_decision_records(records)
        self._events.record(EventName.DECISIONS_EXPORTED)
