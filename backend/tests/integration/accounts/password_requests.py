"""What the tests of password changes, account creations, and password resets share."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass

import httpx

from tests.integration.accounts.admin_requests import KEY
from tests.integration.application import ORIGIN_HEADERS, session_headers
from tests.unit.accounts.fakes import KNOWN_PASSWORD

SESSIONS = "/v1/sessions"
CURRENT_SESSION = "/v1/sessions/current"
OWN_PASSWORD_CHANGES = "/v1/sessions/current/password-changes"
ADMIN_ACCOUNTS = "/v1/admin/accounts"
NEW_PASSWORD = "new-test-password"
WRONG_PASSWORD = "wrong-test-password"
NEW_DISPLAY_NAME = "Lan Do"
NEW_ACCOUNT: Mapping[str, object] = {
    "role": "staff",
    "display_name": NEW_DISPLAY_NAME,
    "password": NEW_PASSWORD,
}
FAILURE_LIMIT = 2
DELAY_MS = 2_000


@dataclass(frozen=True, slots=True)
class OwnChange:
    """The body of `changeOwnPassword`, with the fields of the contract.

    Attributes:
        current_password: The password before the change.
        new_password: The password after it.
        is_signed_out_elsewhere: Whether the other sessions end.
    """

    current_password: str = KNOWN_PASSWORD
    new_password: str = NEW_PASSWORD
    is_signed_out_elsewhere: bool = True


@dataclass(frozen=True, slots=True)
class Reset:
    """The body of `resetAccountPassword`, with the fields of the contract.

    Attributes:
        password: The new password.
        is_signed_out_everywhere: Whether every session ends.
    """

    password: str = NEW_PASSWORD
    is_signed_out_everywhere: bool = True


# The requests that most tests send: to the new password, with every other session ending.
CHANGE_TO_THE_NEW_PASSWORD = OwnChange()
RESET_TO_THE_NEW_PASSWORD = Reset()


def password_reset_path(account_id: object) -> str:
    return f"/v1/admin/accounts/{account_id}/password-resets"


async def sign_in(client: httpx.AsyncClient, login_name: str, password: str) -> httpx.Response:
    return await client.post(
        SESSIONS, json={"login_name": login_name, "password": password}, headers=ORIGIN_HEADERS
    )


async def change_own_password(
    client: httpx.AsyncClient,
    token: str,
    change: OwnChange = CHANGE_TO_THE_NEW_PASSWORD,
    *,
    key: str = KEY,
) -> httpx.Response:
    return await client.post(
        OWN_PASSWORD_CHANGES,
        json=asdict(change),
        headers={**session_headers(token), "Idempotency-Key": key},
    )


async def create_account(
    client: httpx.AsyncClient, token: str, body: Mapping[str, object], *, key: str = KEY
) -> httpx.Response:
    return await client.post(
        ADMIN_ACCOUNTS, json=body, headers={**session_headers(token), "Idempotency-Key": key}
    )


async def reset_password(
    client: httpx.AsyncClient,
    token: str,
    account_id: object,
    reset: Reset = RESET_TO_THE_NEW_PASSWORD,
    *,
    key: str = KEY,
) -> httpx.Response:
    return await client.post(
        password_reset_path(account_id),
        json=asdict(reset),
        headers={**session_headers(token), "Idempotency-Key": key},
    )
