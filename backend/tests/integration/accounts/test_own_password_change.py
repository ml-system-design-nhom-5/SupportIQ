"""`changeOwnPassword` over HTTP against PostgreSQL (ADR-0015, account management design)."""

from http import HTTPStatus
from uuid import UUID

import pytest

from app.accounts import PasswordHash
from tests.integration.accounts.admin_requests import KEY, OTHER_KEY
from tests.integration.accounts.password_requests import (
    CURRENT_SESSION,
    DELAY_MS,
    FAILURE_LIMIT,
    WRONG_PASSWORD,
    OwnChange,
    change_own_password,
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

LOGIN_NAME = "staff-1"


@pytest.fixture
async def owner(builder: DatabaseBuilder, known_password_hash: PasswordHash) -> UUID:
    return await builder.account(
        AccountSpec("staff", login_name=LOGIN_NAME, password_hash=known_password_hash)
    )


async def test_failed_sign_ins_and_wrong_current_passwords_share_the_throttle(
    worker_database: WorkerDatabase,
    builder: DatabaseBuilder,
    owner: UUID,
    known_password_hash: PasswordHash,
) -> None:
    token = await builder.session(owner, "staff")
    clock = FakeClock()
    settings = build_settings(worker_database, sign_in_failure_limit=FAILURE_LIMIT)

    async with running_client(settings, RecordingEventRecorder(), clock) as client:
        await sign_in(client, LOGIN_NAME, WRONG_PASSWORD)
        await change_own_password(client, token, OwnChange(WRONG_PASSWORD), key=KEY)
        response = await change_own_password(client, token, key=OTHER_KEY)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["violated_rule"] == "current_password_incorrect"
    assert clock.sleeps_ms == [DELAY_MS]
    assert (
        await builder.scalar(
            "SELECT password_hash FROM accounts WHERE account_id = :owner", owner=owner
        )
        == known_password_hash
    )


@pytest.mark.parametrize(
    ("is_signed_out_elsewhere", "other_session_status"),
    [(True, HTTPStatus.UNAUTHORIZED), (False, HTTPStatus.OK)],
)
async def test_change_ends_the_other_sessions_only_when_chosen(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    owner: UUID,
    is_signed_out_elsewhere: bool,
    other_session_status: HTTPStatus,
) -> None:
    current = await builder.session(owner, "staff")
    other = await builder.session(owner, "staff")

    await change_own_password(
        backend.client, current, OwnChange(is_signed_out_elsewhere=is_signed_out_elsewhere)
    )
    current_after = await backend.client.get(CURRENT_SESSION, headers=session_headers(current))
    other_after = await backend.client.get(CURRENT_SESSION, headers=session_headers(other))

    assert current_after.status_code == HTTPStatus.OK
    assert other_after.status_code == other_session_status


async def test_change_writes_one_audit_entry_and_a_refused_change_none(
    backend: RunningBackend, builder: DatabaseBuilder, owner: UUID
) -> None:
    token = await builder.session(owner, "staff")

    refused = await change_own_password(backend.client, token, OwnChange(WRONG_PASSWORD), key=KEY)
    changed = await change_own_password(backend.client, token, key=OTHER_KEY)

    assert refused.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert changed.status_code == HTTPStatus.CREATED
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1
    assert await builder.scalar("SELECT event_type FROM audit_log_entries") == (
        "account.password_changed"
    )
    assert await builder.scalar("SELECT actor_account_id FROM audit_log_entries") == owner
    assert await builder.scalar("SELECT data FROM audit_log_entries") == {
        "target_account_id": str(owner),
        "is_signed_out_elsewhere": True,
    }
