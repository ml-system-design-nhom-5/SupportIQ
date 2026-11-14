"""The command line of `backend export-decisions` and the report of a refused output path."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from supportiq_backend.composition_root.cli import (
    EXIT_FAILURE,
    EXIT_SETTINGS_INVALID,
    parse_arguments,
    report_failure,
)
from supportiq_backend.composition_root.report_commands import ExportDecisionsArguments
from supportiq_backend.platform import EventName
from supportiq_backend.reports import ExportPathRefusedError, build_report_period
from tests.unit.platform.fakes import RecordingEventRecorder

START_TEXT = "2026-11-02T00:00:00Z"
END_TEXT = "2026-11-09T00:00:00Z"
OUTPUT = "exports/decisions.jsonl"
PERIOD = build_report_period(datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC))
# argparse ends a usage error with status 2.
EXIT_USAGE_ERROR = EXIT_SETTINGS_INVALID
REFUSED_OUTPUT = Path("../decisions.jsonl")


def export_command(*, start_at: str = START_TEXT, end_at: str = END_TEXT) -> list[str]:
    return ["export-decisions", "--start-at", start_at, "--end-at", end_at, "--output", OUTPUT]


def test_export_takes_the_period_and_the_output_path() -> None:
    arguments = parse_arguments(export_command())

    assert arguments == ExportDecisionsArguments(period=PERIOD, output=Path(OUTPUT))


@pytest.mark.parametrize(
    "command",
    [
        export_command(start_at="2026-11-02"),
        export_command(end_at="2026-11-09T00:00:00+07:00"),
        export_command(end_at=START_TEXT),
        ["export-decisions", "--start-at", START_TEXT, "--end-at", END_TEXT],
    ],
    ids=["start-not-a-timestamp", "end-not-in-utc", "empty-period", "no-output"],
)
def test_export_with_invalid_arguments_stops_with_a_usage_error(command: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        parse_arguments(command)

    assert caught.value.code == EXIT_USAGE_ERROR


def test_export_period_without_duration_explains_the_order_of_the_times(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse_arguments(export_command(end_at=START_TEXT))

    assert "--start-at must be earlier than --end-at" in capsys.readouterr().err


def test_refused_output_path_fails_the_command_and_names_the_path_on_standard_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    events = RecordingEventRecorder()

    status = report_failure(ExportPathRefusedError(REFUSED_OUTPUT), events)

    assert status == EXIT_FAILURE
    assert capsys.readouterr().err == (
        "The output path ../decisions.jsonl is not inside the folder exports/ of the working"
        " directory, so nothing was written.\n"
    )
    (failed,) = events.of(EventName.COMMAND_FAILED)
    assert failed.attributes == {"error_type": "ExportPathRefusedError"}
