"""The `Idempotency-Key` of the writes that take a password, which it never compares (ERR-15).

The same key with other fields than the password returns `409`, and with another password
returns the original result without a second change (account management design, Idempotency).
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus

import httpx
import pytest

from app.accounts import PasswordHash
from tests.integration.accounts.admin_requests import KEY, sign_in_as_new_admin
from tests.integration.accounts.password_requests import (
    ADMIN_ACCOUNTS,
    NEW_ACCOUNT,
    NEW_PASSWORD,
    OWN_PASSWORD_CHANGES,
    password_reset_path,
)
from tests.integration.application import RunningBackend, session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.unit.accounts.fakes import KNOWN_PASSWORD

pytestmark = pytest.mark.anyio

OTHER_PASSWORD = "other-test-password"


@dataclass(frozen=True, slots=True)
class PasswordWrite:
    """One write that takes a password, with three bodies to send with one key.

    Attributes:
        path: The path of the operation.
        token: The session of a role that may call it.
        first: The body of the first request.
        other_password: The same body with other passwords.
        other_field: The same body with another value of a field that is no password.
    """

    path: str
    token: str
    first: Mapping[str, object]
    other_password: Mapping[str, object]
    other_field: Mapping[str, object]


async def own_password_change(
    builder: DatabaseBuilder, password_hash: PasswordHash
) -> PasswordWrite:
    account = await builder.account(AccountSpec("staff", password_hash=password_hash))
    first = {
        "current_password": KNOWN_PASSWORD,
        "new_password": NEW_PASSWORD,
        "is_signed_out_elsewhere": True,
    }
    return PasswordWrite(
        path=OWN_PASSWORD_CHANGES,
        token=await builder.session(account, "staff"),
        first=first,
        other_password={**first, "current_password": NEW_PASSWORD, "new_password": OTHER_PASSWORD},
        other_field={**first, "is_signed_out_elsewhere": False},
    )


async def account_creation(builder: DatabaseBuilder, _password_hash: PasswordHash) -> PasswordWrite:
    _, token = await sign_in_as_new_admin(builder)
    return PasswordWrite(
        path=ADMIN_ACCOUNTS,
        token=token,
        first=NEW_ACCOUNT,
        other_password={**NEW_ACCOUNT, "password": OTHER_PASSWORD},
        other_field={**NEW_ACCOUNT, "display_name": "Minh Le"},
    )


async def password_reset(builder: DatabaseBuilder, _password_hash: PasswordHash) -> PasswordWrite:
    _, token = await sign_in_as_new_admin(builder)
    target = await builder.account(AccountSpec("staff"))
    first = {"password": NEW_PASSWORD, "is_signed_out_everywhere": True}
    return PasswordWrite(
        path=password_reset_path(target),
        token=token,
        first=first,
        other_password={**first, "password": OTHER_PASSWORD},
        other_field={**first, "is_signed_out_everywhere": False},
    )


WRITES: Mapping[str, Callable[[DatabaseBuilder, PasswordHash], Awaitable[PasswordWrite]]] = {
    "changeOwnPassword": own_password_change,
    "createAdminAccount": account_creation,
    "resetAccountPassword": password_reset,
}


@pytest.fixture(params=sorted(WRITES))
async def password_write(
    request: pytest.FixtureRequest, builder: DatabaseBuilder, known_password_hash: PasswordHash
) -> PasswordWrite:
    return await WRITES[request.param](builder, known_password_hash)


async def send(
    client: httpx.AsyncClient, write: PasswordWrite, body: Mapping[str, object]
) -> httpx.Response:
    return await client.post(
        write.path, json=body, headers={**session_headers(write.token), "Idempotency-Key": KEY}
    )


async def test_same_key_with_another_password_returns_the_first_result_and_changes_nothing(
    backend: RunningBackend, builder: DatabaseBuilder, password_write: PasswordWrite
) -> None:
    first = await send(backend.client, password_write, password_write.first)

    repeated = await send(backend.client, password_write, password_write.other_password)

    assert repeated.status_code == HTTPStatus.CREATED
    assert repeated.content == first.content
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1


async def test_same_key_with_another_field_returns_409(
    backend: RunningBackend, password_write: PasswordWrite
) -> None:
    await send(backend.client, password_write, password_write.first)

    response = await send(backend.client, password_write, password_write.other_field)

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["type"] == "urn:supportiq:problem:idempotency-key-reused"
