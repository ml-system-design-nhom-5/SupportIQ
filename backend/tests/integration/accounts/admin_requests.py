"""What the tests of the admin operations share."""

from typing import Literal
from uuid import UUID

import httpx

from tests.integration.application import (
    session_headers,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder

KEY = "00000000-0000-4000-8000-000000000001"
OTHER_KEY = "00000000-0000-4000-8000-000000000002"
UNKNOWN_ACCOUNT = "99999999-9999-4999-8999-999999999999"
SHORT_LOCK_MS = 50
type ChangeKind = Literal["role-changes", "status-changes"]
UPPERCASE_KEY = "0000000A-0000-4000-8000-00000000000A"


def change_path(account_id: object, kind: ChangeKind) -> str:
    return f"/v1/admin/accounts/{account_id}/{kind}"


async def change_role(
    client: httpx.AsyncClient, token: str, account_id: object, role: str, key: str = KEY
) -> httpx.Response:
    return await client.post(
        change_path(account_id, "role-changes"),
        json={"role": role},
        headers={**session_headers(token), "Idempotency-Key": key},
    )


async def change_status(
    client: httpx.AsyncClient, token: str, account_id: object, *, is_active: bool, key: str = KEY
) -> httpx.Response:
    return await client.post(
        change_path(account_id, "status-changes"),
        json={"is_active": is_active},
        headers={**session_headers(token), "Idempotency-Key": key},
    )


async def sign_in_as_new_admin(builder: DatabaseBuilder) -> tuple[UUID, str]:
    account_id = await builder.account(AccountSpec("admin"))
    return account_id, await builder.session(account_id, "admin")
