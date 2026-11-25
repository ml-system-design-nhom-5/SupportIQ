"""Account creations, resets, and own changes that race (account management design, Locks).

A transaction of the test holds a lock that the requests need, so they reach the database at
the same time, and it ends once the requests wait.
"""

import asyncio
from dataclasses import dataclass
from http import HTTPStatus
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts import PasswordHash, SessionToken, hash_session_token
from app.accounts.adapters.internal_accounts import ACCOUNT_CHANGES_LOCK_KEY
from tests.integration.accounts.admin_requests import SHORT_LOCK_MS, sign_in_as_new_admin
from tests.integration.accounts.lock_waits import (
    ADVISORY_LOCK_WAITS,
    ROW_LOCK_WAITS,
    wait_until_waiting,
)
from tests.integration.accounts.password_requests import (
    NEW_ACCOUNT,
    NEW_PASSWORD,
    Reset,
    change_own_password,
    create_account,
    reset_password,
    sign_in,
)
from tests.integration.application import RunningBackend, build_settings, running_client
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.unit.accounts.fakes import KNOWN_PASSWORD
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

LOGIN_NAME = "staff-race"
TAKE_THE_ADVISORY_LOCK = text("SELECT pg_advisory_xact_lock(:key)")
LOCK_A_SESSION = text("SELECT 1 FROM sessions WHERE session_id_hash = :session_id_hash FOR UPDATE")
LOCK_AN_ACCOUNT = text("SELECT 1 FROM accounts WHERE account_id = :account_id FOR UPDATE")
BOTH_REQUESTS = 2


@dataclass(frozen=True, slots=True)
class Race:
    """An account with two sessions, and an admin who resets its password.

    Attributes:
        account_id: The account, whose password is `KNOWN_PASSWORD`.
        current_session: The session of its own password change.
        other_session: Its other session, which the test holds.
        admin_token: The session of the admin.
    """

    account_id: UUID
    current_session: str
    other_session: str
    admin_token: str


@dataclass(frozen=True, slots=True)
class RaceOrder:
    """Which request gets the account's row first, and the password that it leaves.

    Attributes:
        first: The request that holds the row.
        second: The request that waits for it.
        final_password: The password of the account afterwards, the one of the last request.
    """

    first: str
    second: str
    final_password: str


@pytest.fixture
async def race(
    builder: DatabaseBuilder, known_password_hash: PasswordHash, admin_token: str
) -> Race:
    account_id = await builder.account(
        AccountSpec("staff", login_name=LOGIN_NAME, password_hash=known_password_hash)
    )
    return Race(
        account_id=account_id,
        current_session=await builder.session(account_id, "staff"),
        other_session=await builder.session(account_id, "staff"),
        admin_token=admin_token,
    )


async def test_two_creations_without_a_number_get_two_numbers(
    backend: RunningBackend, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    _, first_admin = await sign_in_as_new_admin(builder)
    _, second_admin = await sign_in_as_new_admin(builder)

    async with app_engine.begin() as holder:
        await holder.execute(TAKE_THE_ADVISORY_LOCK, {"key": ACCOUNT_CHANGES_LOCK_KEY})
        first = asyncio.create_task(create_account(backend.client, first_admin, NEW_ACCOUNT))
        second = asyncio.create_task(create_account(backend.client, second_admin, NEW_ACCOUNT))
        await wait_until_waiting(builder, ADVISORY_LOCK_WAITS, BOTH_REQUESTS, first, second)
    responses = await asyncio.gather(first, second)

    assert sorted(response.json()["login_name"] for response in responses) == [
        "staff-1",
        "staff-2",
    ]
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == BOTH_REQUESTS


# The reset sets the password that the own change expects as current, so both succeed in
# either order, and the one that comes last decides the password.
@pytest.mark.parametrize(
    "order",
    [
        RaceOrder("own_change", "reset", KNOWN_PASSWORD),
        RaceOrder("reset", "own_change", NEW_PASSWORD),
    ],
    ids=["own-change-first", "reset-first"],
)
async def test_reset_and_own_change_of_one_account_queue_on_its_row(
    backend: RunningBackend,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    race: Race,
    order: RaceOrder,
) -> None:
    requests = {
        "own_change": lambda: change_own_password(backend.client, race.current_session),
        "reset": lambda: reset_password(
            backend.client, race.admin_token, race.account_id, Reset(KNOWN_PASSWORD)
        ),
    }
    other_session = hash_session_token(SessionToken(race.other_session))

    # Both requests end the other session, so each one holds the account's row while it waits
    # for that session, which the test holds, and the second one then waits for the row.
    async with app_engine.begin() as holder:
        await holder.execute(LOCK_A_SESSION, {"session_id_hash": other_session})
        first = asyncio.create_task(requests[order.first]())
        await wait_until_waiting(builder, ROW_LOCK_WAITS, 1, first)
        second = asyncio.create_task(requests[order.second]())
        await wait_until_waiting(builder, ROW_LOCK_WAITS, BOTH_REQUESTS, first, second)
    responses = await asyncio.gather(first, second)
    signed_in = await sign_in(backend.client, LOGIN_NAME, order.final_password)

    assert [response.status_code for response in responses] == [
        HTTPStatus.CREATED,
        HTTPStatus.CREATED,
    ]
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == BOTH_REQUESTS
    assert signed_in.status_code == HTTPStatus.CREATED


async def test_own_change_never_waits_for_an_admin_change_of_another_account(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    known_password_hash: PasswordHash,
) -> None:
    owner = await builder.account(AccountSpec("staff", password_hash=known_password_hash))
    token = await builder.session(owner, "staff")
    changed_by_an_admin = await builder.account(AccountSpec("staff"))
    settings = build_settings(worker_database, database_lock_timeout_ms=SHORT_LOCK_MS)

    # The test holds what an admin change of another account holds: the advisory lock and
    # the row of that account.
    async with (
        running_client(settings, RecordingEventRecorder(), FakeClock()) as client,
        app_engine.begin() as admin_change,
    ):
        await admin_change.execute(TAKE_THE_ADVISORY_LOCK, {"key": ACCOUNT_CHANGES_LOCK_KEY})
        await admin_change.execute(LOCK_AN_ACCOUNT, {"account_id": changed_by_an_admin})
        response = await change_own_password(client, token)

    assert response.status_code == HTTPStatus.CREATED
