"""The command `backend export-decisions`, run as `supportiq_app` because it only reads.

The output path is checked first, so a path outside `exports/` stops the command before it
connects to the database or writes anything (backend ticket workflow design, The decision-record
export; SEC-33).
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.composition_root.runtime import database_timeouts
from supportiq_backend.platform import EventRecorder, InvalidParameterError
from supportiq_backend.platform.adapters.database import (
    SqlAlchemyTransactionRunner,
    create_database_engine,
    create_session_factory,
)
from supportiq_backend.platform.settings import Settings
from supportiq_backend.reports import (
    ExportDecisions,
    ExportStores,
    InvalidReportPeriodError,
    ReportPeriod,
    build_report_period,
)
from supportiq_backend.reports.adapters.decision_records import PostgresDecisionRecordSource
from supportiq_backend.reports.adapters.export_file import (
    JsonLinesDecisionFile,
    resolve_export_path,
)
from supportiq_backend.reports.api.report_requests import parse_report_timestamp

EXPORT_DECISIONS_COMMAND = "export-decisions"
EXPORT_DECISIONS_HELP = (
    "Write the decision records of a period to a file in exports/, as supportiq_app."
)
# The command reads its times as `getConsoleReport` reads `start_at` and `end_at`.
_TIMESTAMP_FORMAT = "a time in UTC, such as 2026-11-01T00:00:00Z"
_TIMESTAMP_REFUSED = f"must be {_TIMESTAMP_FORMAT}"
_TIMESTAMP_NAME = "timestamp"
_PERIOD_REFUSED = "--start-at must be earlier than --end-at"


@dataclass(frozen=True, slots=True)
class ExportDecisionsArguments:
    """The arguments of `backend export-decisions`.

    Attributes:
        period: The period, from `--start-at`, included, to `--end-at`, excluded.
        output: The output path, as given; it must resolve inside `exports/`.
    """

    period: ReportPeriod
    output: Path


def add_export_decisions_arguments(export_parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of `backend export-decisions`.

    Args:
        export_parser: The parser of the subcommand.
    """
    export_parser.add_argument(
        "--start-at",
        required=True,
        type=_to_timestamp,
        help=f"The start of the period, included: {_TIMESTAMP_FORMAT}.",
    )
    export_parser.add_argument(
        "--end-at",
        required=True,
        type=_to_timestamp,
        help=f"The end of the period, excluded: {_TIMESTAMP_FORMAT}.",
    )
    export_parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="The output file, inside the folder exports/ of the working directory.",
    )


def to_export_decisions_arguments(
    namespace: argparse.Namespace, export_parser: argparse.ArgumentParser
) -> ExportDecisionsArguments:
    """Read the parsed arguments of `backend export-decisions`.

    Args:
        namespace: The parsed command line.
        export_parser: The parser of the subcommand, which reports a usage error.

    Returns:
        The period and the output path.

    Raises:
        SystemExit: `--start-at` is not earlier than `--end-at`; status 2, as for every
            usage error.
    """
    try:
        period = build_report_period(namespace.start_at, namespace.end_at)
    except InvalidReportPeriodError:
        export_parser.error(_PERIOD_REFUSED)
    return ExportDecisionsArguments(period=period, output=Path(namespace.output))


def build_export_stores(session: AsyncSession) -> ExportStores:
    """Build the stores of the export on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return ExportStores(records=PostgresDecisionRecordSource(session))


async def export_decisions(
    settings: Settings,
    events: EventRecorder,
    arguments: ExportDecisionsArguments,
    *,
    working_directory: Path,
) -> None:
    """Write the decision records of the period to a file inside `exports/`.

    Args:
        settings: The validated settings, with `database_url_app`.
        events: Where `decisions.exported` is recorded.
        arguments: The period and the output path.
        working_directory: The folder that holds `exports/`: the working directory.

    Raises:
        ExportPathRefusedError: The output path is not inside `exports/`; nothing was read or
            written.
        DatabaseUnavailableError: The database is not available or a timeout fired.
        ExportWriteFailedError: The file could not be written.
    """
    destination = JsonLinesDecisionFile(resolve_export_path(arguments.output, working_directory))
    engine = create_database_engine(
        settings.database_url_app.get_secret_value(), database_timeouts(settings)
    )
    try:
        transactions = SqlAlchemyTransactionRunner(
            create_session_factory(engine), build_export_stores
        )
        await ExportDecisions(transactions, destination, events).execute(arguments.period)
    finally:
        await engine.dispose()


def _to_timestamp(raw: str) -> datetime:
    try:
        return parse_report_timestamp(raw, _TIMESTAMP_NAME)
    except InvalidParameterError as error:
        raise argparse.ArgumentTypeError(_TIMESTAMP_REFUSED) from error
