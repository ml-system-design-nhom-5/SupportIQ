"""`createAdminAccount` over HTTP against PostgreSQL (ADR-0015, account management design)."""

from http import HTTPStatus
from uuid import UUID

import pytest

from tests.integration.accounts.admin_requests import KEY, OTHER_KEY
from tests.integration.accounts.password_requests import (
    NEW_ACCOUNT,
    NEW_DISPLAY_NAME,
    NEW_PASSWORD,
    create_account,
    sign_in,
)
from tests.integration.application import RunningBackend
from tests.integration.builders import AccountSpec, DatabaseBuilder

pytestmark = pytest.mark.anyio

FIRST_STAFF_LOGIN_NAME = "staff-1"
FIRST_NUMBER = 1
NUMBER_IN_USE = 4


async def test_number_in_use_returns_409_and_creates_nothing(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    # staff-4 became a manager; its login name stays taken.
    await builder.account(AccountSpec("manager", login_name=f"staff-{NUMBER_IN_USE}"))

    response = await create_account(
        backend.client, admin_token, {**NEW_ACCOUNT, "login_number": NUMBER_IN_USE}
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["type"] == "urn:supportiq:problem:login-name-taken"
    assert (
        await builder.scalar(
            "SELECT count(*) FROM accounts WHERE display_name = :name", name=NEW_DISPLAY_NAME
        )
        == 0
    )
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 0


async def test_creation_writes_one_audit_entry_and_a_refused_creation_none(
    backend: RunningBackend, builder: DatabaseBuilder, admin: tuple[UUID, str]
) -> None:
    admin_id, token = admin

    created = await create_account(backend.client, token, NEW_ACCOUNT, key=KEY)
    refused = await create_account(
        backend.client, token, {**NEW_ACCOUNT, "login_number": FIRST_NUMBER}, key=OTHER_KEY
    )

    assert created.json()["login_name"] == FIRST_STAFF_LOGIN_NAME
    assert refused.status_code == HTTPStatus.CONFLICT
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1
    assert await builder.scalar("SELECT event_type FROM audit_log_entries") == "account.created"
    assert await builder.scalar("SELECT actor_account_id FROM audit_log_entries") == admin_id
    assert await builder.scalar("SELECT data FROM audit_log_entries") == {
        "target_account_id": created.json()["account_id"],
        "role": "staff",
    }


async def test_created_account_signs_in_with_the_password_of_the_creation(
    backend: RunningBackend, admin_token: str
) -> None:
    created = await create_account(backend.client, admin_token, NEW_ACCOUNT)

    signed_in = await sign_in(backend.client, created.json()["login_name"], NEW_PASSWORD)

    assert signed_in.status_code == HTTPStatus.CREATED
    assert signed_in.json()["account_id"] == created.json()["account_id"]
    assert signed_in.json()["role"] == "staff"
