"""`backend export-decisions` as a process: exit statuses, what it prints, and what it writes.

The command runs in a temporary working directory, so its `exports/` folder is that
directory's, and it connects as `supportiq_app` with the environment of the other command
tests.
"""

import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.integration.composition_root.test_backend_command import (
    BACKEND_COMMAND,
    COMMAND_TIMEOUT_S,
    EXIT_FAILURE,
    EXIT_SUCCESS,
    build_environment,
)
from tests.integration.database import WorkerDatabase
from tests.integration.reports.export_scenario import ExportTickets, insert_export_scenario
from tests.integration.reports.report_rows import END_TEXT, START_TEXT, ReportRows

pytestmark = pytest.mark.anyio

OUTPUT = "exports/decisions.jsonl"
REFUSED_OUTPUT = "../decisions.jsonl"
EXIT_USAGE_ERROR = 2


@dataclass(frozen=True, slots=True)
class ExportRun:
    """What a run of the command left.

    Attributes:
        status: The exit status.
        events: The `event` of every JSON line on standard output.
        errors: Standard error.
    """

    status: int | None
    events: list[str]
    errors: str


async def run_export(
    worker_database: WorkerDatabase,
    working_directory: Path,
    output: str = OUTPUT,
    end_at: str = END_TEXT,
) -> ExportRun:
    process = await asyncio.create_subprocess_exec(
        BACKEND_COMMAND,
        "export-decisions",
        "--start-at",
        START_TEXT,
        "--end-at",
        end_at,
        "--output",
        output,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=build_environment(worker_database),
        cwd=working_directory,
    )
    async with asyncio.timeout(COMMAND_TIMEOUT_S):
        output_bytes, error_bytes = await process.communicate()
    events = [json.loads(line)["event"] for line in output_bytes.decode().splitlines()]
    return ExportRun(process.returncode, events, error_bytes.decode())


def names_under(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.rglob("*"))


@pytest.fixture
async def tickets(rows: ReportRows) -> ExportTickets:
    return await insert_export_scenario(rows)


async def test_export_writes_the_records_and_exits_with_success(
    worker_database: WorkerDatabase, tmp_path: Path, tickets: ExportTickets
) -> None:
    run = await run_export(worker_database, tmp_path)

    lines = (tmp_path / OUTPUT).read_text(encoding="utf-8").splitlines()
    assert run.status == EXIT_SUCCESS
    assert "decisions.exported" in run.events
    assert [json.loads(line)["ticket_id"] for line in lines] == [
        tickets.closed,
        tickets.escalated,
        tickets.manual,
        tickets.failed,
    ]


@pytest.mark.usefixtures("tickets")
async def test_export_to_a_path_outside_exports_fails_names_the_path_and_writes_nothing(
    worker_database: WorkerDatabase, tmp_path: Path
) -> None:
    working_directory = tmp_path / "work"
    working_directory.mkdir()

    run = await run_export(worker_database, working_directory, REFUSED_OUTPUT)

    assert run.status == EXIT_FAILURE
    assert "command.failed" in run.events
    assert REFUSED_OUTPUT in run.errors
    assert names_under(tmp_path) == ["work"]


async def test_export_of_a_period_without_duration_stops_with_a_usage_error(
    worker_database: WorkerDatabase, tmp_path: Path
) -> None:
    run = await run_export(worker_database, tmp_path, end_at=START_TEXT)

    assert run.status == EXIT_USAGE_ERROR
    assert "--start-at must be earlier than --end-at" in run.errors
    assert not (tmp_path / "exports").exists()
