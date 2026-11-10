"""Account changes that race: the advisory lock serializes them (ADR-0012, SEC-42)."""

import asyncio
from http import HTTPStatus

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import AccountId, LoginName, NewSession, Role, SessionIdHash
from supportiq_backend.accounts.adapters.internal_accounts import ACCOUNT_CHANGES_LOCK_KEY
from supportiq_backend.composition_root.accounts_wiring import build_sign_in_stores
from supportiq_backend.platform.adapters.database import (
    SqlAlchemyTransactionRunner,
    create_session_factory,
)
from tests.integration.accounts.admin_requests import (
    SHORT_LOCK_MS,
    change_role,
    change_status,
    sign_in_as_new_admin,
)
from tests.integration.application import (
    RunningBackend,
    build_settings,
    running_client,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

WAITS_FOR_A_ROW_LOCK = """
    SELECT count(*)
    FROM pg_locks AS waiting
    JOIN pg_stat_activity AS activity USING (pid)
    WHERE NOT waiting.granted
      AND waiting.locktype = 'transactionid'
      AND activity.datname = current_database()
"""


async def wait_until_it_waits_for_a_row_lock(
    builder: DatabaseBuilder, request: asyncio.Task[httpx.Response]
) -> None:
    # Each read is its own transaction, so it sees the current locks. The round trip to
    # PostgreSQL gives the request its turn, so this loop needs no sleep (TEST-14), and the lock
    # timeout of the application ends the request if it never gets past the row lock.
    while not request.done():
        if await builder.scalar(WAITS_FOR_A_ROW_LOCK) != 0:
            return
    pytest.fail("The request ended without waiting for the row lock of the sign-in.")


async def test_two_admins_demoting_the_last_two_managers_leave_one(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    first_manager = await builder.account(AccountSpec("manager"))
    second_manager = await builder.account(AccountSpec("manager"))
    _, first_admin = await sign_in_as_new_admin(builder)
    _, second_admin = await sign_in_as_new_admin(builder)

    responses = await asyncio.gather(
        change_role(backend.client, first_admin, first_manager, "staff"),
        change_role(backend.client, second_admin, second_manager, "staff"),
    )

    assert sorted(response.status_code for response in responses) == [
        HTTPStatus.CREATED,
        HTTPStatus.UNPROCESSABLE_CONTENT,
    ]
    assert (
        await builder.scalar("SELECT count(*) FROM accounts WHERE role = 'manager' AND is_active")
        == 1
    )
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1


async def test_two_admins_deactivating_each_other_leave_one_active(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    first_id, first_admin = await sign_in_as_new_admin(builder)
    second_id, second_admin = await sign_in_as_new_admin(builder)

    responses = await asyncio.gather(
        change_status(backend.client, first_admin, second_id, is_active=False),
        change_status(backend.client, second_admin, first_id, is_active=False),
    )

    assert sorted(response.status_code for response in responses) == [
        HTTPStatus.CREATED,
        HTTPStatus.UNAUTHORIZED,
    ]
    assert (
        await builder.scalar("SELECT count(*) FROM accounts WHERE role = 'admin' AND is_active")
        == 1
    )
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1


async def test_deactivation_during_a_sign_in_leaves_no_session(
    backend: RunningBackend,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    admin_token: str,
) -> None:
    target = await builder.account(AccountSpec("staff", login_name="staff-race"))
    runner = SqlAlchemyTransactionRunner(create_session_factory(app_engine), build_sign_in_stores)
    now = backend.clock.now()

    async with runner.begin() as sign_in:
        account = await sign_in.stores.accounts.load_for_sign_in(LoginName("staff-race"))
        assert account is not None
        await sign_in.stores.sessions.save(
            NewSession(SessionIdHash(b"h" * 32), AccountId(str(target)), Role.STAFF, now, now)
        )
        deactivation = asyncio.create_task(
            change_status(backend.client, admin_token, target, is_active=False)
        )
        await wait_until_it_waits_for_a_row_lock(builder, deactivation)
        await sign_in.commit()

    response = await deactivation

    assert response.status_code == HTTPStatus.CREATED
    assert (
        await builder.scalar(
            "SELECT count(*) FROM sessions WHERE account_id = :target", target=target
        )
        == 0
    )


async def test_wait_for_the_advisory_lock_longer_than_the_timeout_returns_503(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    admin_token: str,
) -> None:
    target = await builder.account(AccountSpec("staff"))
    settings = build_settings(worker_database, database_lock_timeout_ms=SHORT_LOCK_MS)

    async with (
        running_client(settings, RecordingEventRecorder(), FakeClock()) as client,
        app_engine.begin() as holder,
    ):
        await holder.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_CHANGES_LOCK_KEY}
        )
        response = await change_role(client, admin_token, target, "manager")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 0
