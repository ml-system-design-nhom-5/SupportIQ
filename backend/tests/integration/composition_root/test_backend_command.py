"""The `backend` command as a process: exit statuses, confirmation, and what it prints."""

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase

pytestmark = pytest.mark.anyio

BACKEND_COMMAND = Path(sys.executable).parent / "backend"
BACKEND_ROOT = Path(__file__).parents[3]
COMMAND_TIMEOUT_S = 60
CUSTOMER_PASSWORD = "command-customer-test-password"
STAFF_PASSWORD = "command-staff-test-password"
MANAGER_PASSWORD = "command-manager-test-password"
ADMIN_PASSWORD = "command-admin-test-password"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_SETTINGS_INVALID = 2
SEEDED_ACCOUNTS = 9
CLOSED_PORT_URL = "postgresql+asyncpg://supportiq_owner:x@127.0.0.1:1/supportiq"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What a run of the command left.

    Attributes:
        status: The exit status.
        output: Standard output, which holds the JSON log lines.
        errors: Standard error.
    """

    status: int | None
    output: str
    errors: str


def build_environment(worker_database: WorkerDatabase) -> dict[str, str]:
    return {
        "DATABASE_URL_OWNER": worker_database.owner_url,
        "DATABASE_URL_APP": worker_database.app_url,
        # The test cluster runs on the same host without TLS (README, TLS to the database).
        "DATABASE_TLS": "disable",
        "ALLOWED_ORIGINS": '["http://shop.test"]',
        "SEED_PASSWORD_CUSTOMER": CUSTOMER_PASSWORD,
        "SEED_PASSWORD_STAFF": STAFF_PASSWORD,
        "SEED_PASSWORD_MANAGER": MANAGER_PASSWORD,
        "SEED_PASSWORD_ADMIN": ADMIN_PASSWORD,
        "AI_SERVICE_BASE_URL": "http://ai-service.invalid",
        "AI_SERVICE_TOKEN": "command-test-ai-service-token",
        "BACKEND_BUILD_VERSION": "command-test-build",
    }


async def run_backend(
    environment: dict[str, str], *arguments: str, answer: str = ""
) -> CommandResult:
    process = await asyncio.create_subprocess_exec(
        BACKEND_COMMAND,
        *arguments,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        cwd=BACKEND_ROOT,
    )
    async with asyncio.timeout(COMMAND_TIMEOUT_S):
        output, errors = await process.communicate(answer.encode())
    return CommandResult(process.returncode, output.decode(), errors.decode())


@pytest.fixture
def environment(worker_database: WorkerDatabase) -> dict[str, str]:
    return build_environment(worker_database)


async def count_accounts(builder: DatabaseBuilder) -> object:
    return await builder.scalar("SELECT count(*) FROM accounts")


async def test_migrate_prints_json_lines_and_exits_with_success(
    environment: dict[str, str],
) -> None:
    result = await run_backend(environment, "migrate")

    assert result.status == EXIT_SUCCESS
    assert '"event":"database.migrated"' in result.output


async def test_seed_loads_the_file_without_printing_a_password(
    environment: dict[str, str], builder: DatabaseBuilder
) -> None:
    result = await run_backend(environment, "seed")

    assert result.status == EXIT_SUCCESS
    assert '"event":"seed.loaded"' in result.output
    assert await count_accounts(builder) == SEEDED_ACCOUNTS
    assert "test-password" not in result.output


async def test_seed_on_a_seeded_database_exits_with_a_failure(
    environment: dict[str, str],
) -> None:
    await run_backend(environment, "seed")

    result = await run_backend(environment, "seed")

    assert result.status == EXIT_FAILURE
    assert '"event":"command.failed"' in result.output


async def test_reset_with_yes_runs_without_a_question(
    environment: dict[str, str], builder: DatabaseBuilder
) -> None:
    await run_backend(environment, "seed")

    result = await run_backend(environment, "reset", "--yes")

    assert result.status == EXIT_SUCCESS
    assert '"event":"seed.reset"' in result.output
    assert await count_accounts(builder) == SEEDED_ACCOUNTS


async def test_reset_runs_after_the_answer_yes(environment: dict[str, str]) -> None:
    await run_backend(environment, "seed")

    result = await run_backend(environment, "reset", answer="yes\n")

    assert result.status == EXIT_SUCCESS
    assert '"event":"seed.reset"' in result.output
    assert "Type yes to go on" in result.errors


@pytest.mark.parametrize("answer", ["no\n", ""], ids=["no", "closed-input"])
async def test_reset_without_the_answer_yes_is_cancelled_and_empties_nothing(
    environment: dict[str, str], builder: DatabaseBuilder, answer: str
) -> None:
    await builder.account(AccountSpec("staff"))

    result = await run_backend(environment, "reset", answer=answer)

    assert result.status == EXIT_SUCCESS
    assert '"event":"seed.reset_cancelled"' in result.output
    assert await count_accounts(builder) == 1


async def test_missing_setting_stops_the_command_and_names_the_setting(
    environment: dict[str, str],
) -> None:
    del environment["DATABASE_URL_APP"]

    result = await run_backend(environment, "migrate")

    assert result.status == EXIT_SETTINGS_INVALID
    assert '"event":"settings.invalid"' in result.output
    assert "database_url_app" in result.output


async def test_missing_seed_password_stops_the_seed_and_names_the_setting(
    environment: dict[str, str], builder: DatabaseBuilder
) -> None:
    del environment["SEED_PASSWORD_ADMIN"]

    result = await run_backend(environment, "seed")

    assert result.status == EXIT_SETTINGS_INVALID
    assert "seed_password_admin" in result.output
    assert await count_accounts(builder) == 0


async def test_owner_database_that_cannot_be_reached_exits_with_a_failure_and_no_traceback(
    environment: dict[str, str],
) -> None:
    environment["DATABASE_URL_OWNER"] = CLOSED_PORT_URL

    result = await run_backend(environment, "migrate")

    assert result.status == EXIT_FAILURE
    assert '"event":"command.failed"' in result.output
    assert result.errors == ""


@pytest.mark.parametrize(
    ("arguments", "without_setting"),
    [
        (("migrate",), None),
        (("reset",), None),
        (("seed",), "SEED_PASSWORD_ADMIN"),
        (("migrate",), "DATABASE_URL_APP"),
    ],
    ids=["success", "cancelled", "failure", "settings-invalid"],
)
async def test_every_line_of_a_command_carries_a_trace_id(
    environment: dict[str, str], arguments: tuple[str, ...], without_setting: str | None
) -> None:
    environment.pop(without_setting or "", None)

    result = await run_backend(environment, *arguments)

    lines = [json.loads(line) for line in result.output.splitlines()]
    assert lines != []
    assert [line["event"] for line in lines if "trace_id" not in line] == []
