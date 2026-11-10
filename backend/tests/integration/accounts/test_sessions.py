"""`getCurrentSession` and `deleteCurrentSession` over HTTP (ADR-0009, design step 3 and 4)."""

from datetime import timedelta
from http import HTTPStatus
from uuid import UUID

import pytest

from tests.integration.application import ORIGIN_HEADERS, RunningBackend, session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

CURRENT_SESSION = "/v1/sessions/current"
DISPLAY_NAME = "Mai Nguyen"
NO_SESSION_DETAIL = "The request has no valid session."
IDLE_TIMEOUT_MS = 1_800_000
TOUCH_INTERVAL_MS = 60_000


@pytest.fixture
async def account_id(builder: DatabaseBuilder) -> UUID:
    return await builder.account(AccountSpec("staff", display_name=DISPLAY_NAME))


async def test_current_session_returns_the_account(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    token = await builder.session(account_id, "staff")

    response = await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "account_id": str(account_id),
        "display_name": DISPLAY_NAME,
        "role": "staff",
    }


async def test_current_session_of_a_customer_returns_its_role(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    account_id, _ = await builder.customer_account()
    token = await builder.session(account_id, "customer")

    response = await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    assert response.json()["role"] == "customer"


async def test_request_without_a_cookie_gets_401(backend: RunningBackend) -> None:
    response = await backend.client.get(CURRENT_SESSION)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["detail"] == NO_SESSION_DETAIL


async def test_unknown_cookie_gets_401(backend: RunningBackend) -> None:
    response = await backend.client.get(CURRENT_SESSION, headers=session_headers("unknown"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_idle_session_gets_401_and_is_deleted(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    token = await builder.session(account_id, "staff")
    backend.clock.advance(IDLE_TIMEOUT_MS)

    response = await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert await builder.scalar("SELECT count(*) FROM sessions") == 0


async def test_session_past_its_lifetime_gets_401_and_is_deleted(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    token = await builder.session(account_id, "staff", expires_at=FAKE_CLOCK_START)

    response = await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert await builder.scalar("SELECT count(*) FROM sessions") == 0


async def test_session_of_a_deactivated_account_gets_401_and_is_deleted(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    account_id = await builder.account(AccountSpec("staff", is_active=False))
    token = await builder.session(account_id, "staff")

    response = await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert await builder.scalar("SELECT count(*) FROM sessions") == 0


async def test_read_within_the_touch_interval_keeps_last_seen_at(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    token = await builder.session(account_id, "staff")
    backend.clock.advance(TOUCH_INTERVAL_MS - 1)

    await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    assert await builder.scalar("SELECT last_seen_at FROM sessions") == FAKE_CLOCK_START


async def test_read_after_the_touch_interval_updates_last_seen_at(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    token = await builder.session(account_id, "staff")
    backend.clock.advance(TOUCH_INTERVAL_MS)

    await backend.client.get(CURRENT_SESSION, headers=session_headers(token))

    last_seen_at = await builder.scalar("SELECT last_seen_at FROM sessions")
    assert last_seen_at == FAKE_CLOCK_START + timedelta(milliseconds=TOUCH_INTERVAL_MS)


async def test_sign_out_deletes_the_session_and_a_retry_gets_401(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    token = await builder.session(account_id, "staff")

    signed_out = await backend.client.delete(CURRENT_SESSION, headers=session_headers(token))
    retried = await backend.client.delete(CURRENT_SESSION, headers=session_headers(token))

    assert signed_out.status_code == HTTPStatus.NO_CONTENT
    assert signed_out.content == b""
    assert "set-cookie" not in signed_out.headers
    assert retried.status_code == HTTPStatus.UNAUTHORIZED
    assert await builder.scalar("SELECT count(*) FROM sessions") == 0


async def test_sign_out_without_an_allowed_origin_changes_nothing(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    token = await builder.session(account_id, "staff")

    response = await backend.client.delete(
        CURRENT_SESSION, headers={"Cookie": f"supportiq_session={token}"}
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert await builder.scalar("SELECT count(*) FROM sessions") == 1


async def test_origin_check_runs_before_authentication(backend: RunningBackend) -> None:
    response = await backend.client.delete(CURRENT_SESSION)

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_sign_out_without_a_session_gets_401(backend: RunningBackend) -> None:
    response = await backend.client.delete(CURRENT_SESSION, headers=ORIGIN_HEADERS)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
