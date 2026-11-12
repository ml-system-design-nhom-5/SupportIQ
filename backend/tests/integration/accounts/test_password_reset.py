"""`resetAccountPassword` over HTTP against PostgreSQL (ADR-0015, account management design)."""

from http import HTTPStatus
from uuid import UUID

import pytest

from tests.integration.accounts.admin_requests import KEY, OTHER_KEY
from tests.integration.accounts.password_requests import (
    CURRENT_SESSION,
    FAILURE_LIMIT,
    NEW_PASSWORD,
    WRONG_PASSWORD,
    Reset,
    reset_password,
    sign_in,
)
from tests.integration.application import (
    RunningBackend,
    build_settings,
    running_client,
    session_headers,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

TARGET_LOGIN_NAME = "staff-2"


@pytest.mark.parametrize(
    ("is_signed_out_everywhere", "session_status"),
    [(True, HTTPStatus.UNAUTHORIZED), (False, HTTPStatus.OK)],
)
async def test_reset_ends_every_session_only_when_chosen(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    admin_token: str,
    is_signed_out_everywhere: bool,
    session_status: HTTPStatus,
) -> None:
    target = await builder.account(AccountSpec("staff"))
    token = await builder.session(target, "staff")

    await reset_password(
        backend.client,
        admin_token,
        target,
        Reset(is_signed_out_everywhere=is_signed_out_everywhere),
    )
    after = await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    assert after.status_code == session_status


async def test_reset_at_the_failure_limit_lets_the_owner_sign_in_at_once(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff", login_name=TARGET_LOGIN_NAME))
    clock = FakeClock()
    settings = build_settings(worker_database, sign_in_failure_limit=FAILURE_LIMIT)

    async with running_client(settings, RecordingEventRecorder(), clock) as client:
        await sign_in(client, TARGET_LOGIN_NAME, WRONG_PASSWORD)
        await sign_in(client, TARGET_LOGIN_NAME, WRONG_PASSWORD)
        await reset_password(client, admin_token, target)
        response = await sign_in(client, TARGET_LOGIN_NAME, NEW_PASSWORD)

    assert response.status_code == HTTPStatus.CREATED
    assert clock.sleeps_ms == []


async def test_reset_writes_one_audit_entry_and_a_refused_reset_none(
    backend: RunningBackend, builder: DatabaseBuilder, admin: tuple[UUID, str]
) -> None:
    admin_id, token = admin
    target = await builder.account(AccountSpec("staff"))

    refused = await reset_password(backend.client, token, admin_id, key=KEY)
    reset = await reset_password(backend.client, token, target, key=OTHER_KEY)

    assert refused.json()["violated_rule"] == "own_account"
    assert reset.status_code == HTTPStatus.CREATED
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1
    assert await builder.scalar("SELECT event_type FROM audit_log_entries") == (
        "account.password_reset"
    )
    assert await builder.scalar("SELECT actor_account_id FROM audit_log_entries") == admin_id
    assert await builder.scalar("SELECT data FROM audit_log_entries") == {
        "target_account_id": str(target),
        "is_signed_out_everywhere": True,
    }
