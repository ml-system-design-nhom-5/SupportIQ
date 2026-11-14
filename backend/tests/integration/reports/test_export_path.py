"""The output path of the export: only inside `exports/`, and nothing written otherwise (SEC-33).

A refused path stops `export_decisions` before it connects or writes, so the database rows of
the scenario are never read and no file appears anywhere.
"""

from pathlib import Path

import pytest

from supportiq_backend.composition_root.report_commands import (
    ExportDecisionsArguments,
    export_decisions,
)
from supportiq_backend.reports import ExportPathRefusedError, build_report_period
from supportiq_backend.reports.adapters.export_file import resolve_export_path
from tests.integration.application import build_settings
from tests.integration.database import WorkerDatabase
from tests.integration.reports.export_scenario import insert_export_scenario
from tests.integration.reports.report_rows import END_AT, START_AT, ReportRows
from tests.unit.platform.fakes import RecordingEventRecorder

pytestmark = pytest.mark.anyio

PERIOD = build_report_period(START_AT, END_AT)
WORK = "work"
OUTSIDE = "outside"
FILE_NAME = "decisions.jsonl"


@pytest.fixture
def working_directory(tmp_path: Path) -> Path:
    directory = tmp_path / WORK
    directory.mkdir()
    (tmp_path / OUTSIDE).mkdir()
    return directory


def files_under(tmp_path: Path) -> list[Path]:
    return sorted(path for path in tmp_path.rglob("*") if path.is_file())


@pytest.mark.parametrize(
    "output",
    [
        Path(FILE_NAME),
        Path("../decisions.jsonl"),
        Path("exports/../decisions.jsonl"),
        Path("exports/../../outside/decisions.jsonl"),
        Path("exports"),
        Path("exported/decisions.jsonl"),
    ],
    ids=["working-directory", "parent", "dot-dot", "dot-dot-twice", "folder", "name-prefix"],
)
def test_relative_path_outside_exports_is_refused_and_named(
    working_directory: Path, output: Path
) -> None:
    with pytest.raises(ExportPathRefusedError) as caught:
        resolve_export_path(output, working_directory)

    assert str(output) in caught.value.detail


def test_absolute_path_outside_exports_is_refused(working_directory: Path, tmp_path: Path) -> None:
    output = tmp_path / OUTSIDE / FILE_NAME

    with pytest.raises(ExportPathRefusedError):
        resolve_export_path(output, working_directory)


def test_absolute_path_inside_exports_is_accepted(working_directory: Path) -> None:
    output = working_directory / "exports" / FILE_NAME

    resolved = resolve_export_path(output, working_directory)

    assert resolved == working_directory.resolve() / "exports" / FILE_NAME


def test_link_inside_exports_that_leads_outside_is_refused(
    working_directory: Path, tmp_path: Path
) -> None:
    (working_directory / "exports").mkdir()
    (working_directory / "exports" / FILE_NAME).symlink_to(tmp_path / OUTSIDE / FILE_NAME)

    with pytest.raises(ExportPathRefusedError):
        resolve_export_path(Path("exports") / FILE_NAME, working_directory)


def test_exports_folder_that_is_a_link_to_another_folder_is_refused(
    working_directory: Path, tmp_path: Path
) -> None:
    (working_directory / "exports").symlink_to(tmp_path / OUTSIDE, target_is_directory=True)

    with pytest.raises(ExportPathRefusedError):
        resolve_export_path(Path("exports") / FILE_NAME, working_directory)


@pytest.mark.parametrize(
    "output",
    [Path("../outside/decisions.jsonl"), Path("exports/../../outside/decisions.jsonl")],
    ids=["parent", "dot-dot"],
)
async def test_refused_export_writes_nothing_and_records_nothing(
    worker_database: WorkerDatabase,
    rows: ReportRows,
    tmp_path: Path,
    working_directory: Path,
    output: Path,
) -> None:
    await insert_export_scenario(rows)
    events = RecordingEventRecorder()

    with pytest.raises(ExportPathRefusedError):
        await export_decisions(
            build_settings(worker_database),
            events,
            ExportDecisionsArguments(period=PERIOD, output=output),
            working_directory=working_directory,
        )

    assert files_under(tmp_path) == []
    assert events.names() == ()
