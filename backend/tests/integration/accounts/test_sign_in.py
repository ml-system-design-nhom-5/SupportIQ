"""`createSession` over HTTP against PostgreSQL, step by step of the design's diagram."""

import hashlib
from http import HTTPStatus
from uuid import UUID

import httpx
import pytest

from app.accounts import PasswordHash
from app.platform import EventName
from tests.integration.application import (
    ALLOWED_ORIGIN,
    ORIGIN_HEADERS,
    RunningBackend,
    build_settings,
    running_client,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.unit.accounts.fakes import KNOWN_PASSWORD
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

LOGIN_NAME = "staff-1"
DISPLAY_NAME = "Mai Nguyen"
UNREACHABLE_URL = "postgresql+asyncpg://supportiq_app:x@127.0.0.1:1/supportiq"
FAILURE_LIMIT = 2
DELAY_MS = 2_000
NOT_VALID_DETAIL = "The login name or the password is not valid."


def credentials(login_name: str = LOGIN_NAME, password: str = KNOWN_PASSWORD) -> dict[str, str]:
    return {"login_name": login_name, "password": password}


async def sign_in(client: httpx.AsyncClient, body: dict[str, str]) -> httpx.Response:
    return await client.post("/v1/sessions", json=body, headers=ORIGIN_HEADERS)


def without_trace_id(response: httpx.Response) -> dict[str, object]:
    return {name: value for name, value in response.json().items() if name != "trace_id"}


@pytest.fixture
async def account_id(builder: DatabaseBuilder, known_password_hash: PasswordHash) -> UUID:
    return await builder.account(
        AccountSpec(
            "staff",
            login_name=LOGIN_NAME,
            display_name=DISPLAY_NAME,
            password_hash=known_password_hash,
        )
    )


async def test_valid_credentials_return_the_session_view(
    backend: RunningBackend, account_id: UUID
) -> None:
    response = await sign_in(backend.client, credentials())

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        "account_id": str(account_id),
        "display_name": DISPLAY_NAME,
        "role": "staff",
    }


@pytest.mark.usefixtures("account_id")
async def test_cookie_has_the_attributes_of_adr_0009(backend: RunningBackend) -> None:
    response = await sign_in(backend.client, credentials())

    cookie = response.headers["set-cookie"].lower()

    assert cookie.startswith("supportiq_session=")
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie
    assert "max-age" not in cookie
    assert "expires" not in cookie
    assert "secure" not in cookie


@pytest.mark.usefixtures("account_id")
async def test_cookie_is_secure_with_the_initial_value_of_the_setting(
    worker_database: WorkerDatabase,
) -> None:
    settings = build_settings(worker_database, session_cookie_secure=True)

    async with running_client(settings, RecordingEventRecorder(), FakeClock()) as client:
        response = await sign_in(client, credentials())

    assert "secure" in response.headers["set-cookie"].lower()


@pytest.mark.usefixtures("account_id")
async def test_sessions_table_holds_only_the_hash_of_the_identifier(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    response = await sign_in(backend.client, credentials())
    raw_identifier = response.cookies["supportiq_session"]

    stored_hash = await builder.scalar("SELECT session_id_hash FROM sessions")

    assert stored_hash == hashlib.sha256(raw_identifier.encode()).digest()
    assert raw_identifier.encode() != stored_hash


async def test_login_name_is_normalized_before_the_lookup(
    backend: RunningBackend, account_id: UUID
) -> None:
    response = await sign_in(backend.client, credentials(login_name="  STAFF-1 "))

    assert response.json()["account_id"] == str(account_id)


async def test_success_deletes_expired_sessions_and_the_failures_of_the_name(
    backend: RunningBackend, builder: DatabaseBuilder, account_id: UUID
) -> None:
    await sign_in(backend.client, credentials(password="wrong-test-password"))
    await builder.session(account_id, "staff", expires_at=backend.clock.now())

    await sign_in(backend.client, credentials())

    assert await builder.scalar("SELECT count(*) FROM sessions") == 1
    assert await builder.scalar("SELECT count(*) FROM sign_in_failures") == 0


async def test_unknown_name_wrong_password_and_deactivated_account_look_the_same(
    backend: RunningBackend, builder: DatabaseBuilder, known_password_hash: PasswordHash
) -> None:
    await builder.account(
        AccountSpec("staff", login_name=LOGIN_NAME, password_hash=known_password_hash)
    )
    await builder.account(
        AccountSpec(
            "staff", login_name="staff-2", is_active=False, password_hash=known_password_hash
        )
    )

    unknown = await sign_in(backend.client, credentials(login_name="staff-999"))
    wrong = await sign_in(backend.client, credentials(password="wrong-test-password"))
    deactivated = await sign_in(backend.client, credentials(login_name="staff-2"))

    assert unknown.status_code == HTTPStatus.UNAUTHORIZED
    assert wrong.status_code == HTTPStatus.UNAUTHORIZED
    assert deactivated.status_code == HTTPStatus.UNAUTHORIZED
    assert without_trace_id(unknown) == without_trace_id(wrong) == without_trace_id(deactivated)
    assert unknown.json()["detail"] == NOT_VALID_DETAIL
    assert "set-cookie" not in unknown.headers


async def test_login_name_with_a_nul_character_fails_like_an_unknown_name(
    backend: RunningBackend,
) -> None:
    nul = await sign_in(backend.client, credentials(login_name="staff\x00"))
    unknown = await sign_in(backend.client, credentials(login_name="staff-999"))

    assert nul.status_code == HTTPStatus.UNAUTHORIZED
    assert without_trace_id(nul) == without_trace_id(unknown)


async def test_every_failure_is_counted_by_the_hash_of_the_typed_name(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    await sign_in(backend.client, credentials(login_name="Staff-999"))

    stored_hash = await builder.scalar("SELECT login_name_hash FROM sign_in_failures")

    assert stored_hash == hashlib.sha256(b"staff-999").digest()


@pytest.mark.usefixtures("account_id")
async def test_at_the_limit_even_the_right_password_waits_and_gets_401(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    clock = FakeClock()
    settings = build_settings(worker_database, sign_in_failure_limit=FAILURE_LIMIT)

    async with running_client(settings, RecordingEventRecorder(), clock) as client:
        await sign_in(client, credentials(password="wrong-test-password"))
        await sign_in(client, credentials(password="wrong-test-password"))
        response = await sign_in(client, credentials())

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["detail"] == NOT_VALID_DETAIL
    assert clock.sleeps_ms == [DELAY_MS]
    assert await builder.scalar("SELECT count(*) FROM sessions") == 0


async def test_unknown_name_is_throttled_exactly_like_a_known_one(
    worker_database: WorkerDatabase,
) -> None:
    clock = FakeClock()
    settings = build_settings(worker_database, sign_in_failure_limit=FAILURE_LIMIT)
    unknown = credentials(login_name="staff-999")

    async with running_client(settings, RecordingEventRecorder(), clock) as client:
        await sign_in(client, unknown)
        await sign_in(client, unknown)
        response = await sign_in(client, unknown)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert clock.sleeps_ms == [DELAY_MS]


@pytest.mark.usefixtures("account_id")
async def test_failures_older_than_the_window_are_deleted_by_the_next_failure(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    await sign_in(backend.client, credentials(password="wrong-test-password"))
    backend.clock.advance(900_000)

    await sign_in(backend.client, credentials(password="wrong-test-password"))

    assert await builder.scalar("SELECT count(*) FROM sign_in_failures") == 1


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "http://evil.test"}, {"Origin": "null"}],
    ids=["missing", "unknown", "null"],
)
@pytest.mark.usefixtures("account_id")
async def test_request_without_an_allowed_origin_is_refused_and_changes_nothing(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    response = await backend.client.post("/v1/sessions", json=credentials(), headers=headers)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["detail"] == "The Origin header is missing or not allowed."
    assert await builder.scalar("SELECT count(*) FROM sessions") == 0


async def test_origin_check_runs_before_the_body_is_read(backend: RunningBackend) -> None:
    response = await backend.client.post(
        "/v1/sessions", content=b"{not json", headers={"Origin": "http://evil.test"}
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    "body",
    [
        b"{not json",
        b"",
        b"[]",
        b'{"login_name": "staff-1"}',
        b'{"password": "x"}',
        b'{"login_name": "", "password": "x"}',
        b'{"login_name": "staff-1", "password": ""}',
        b'{"login_name": "staff-1", "password": "x", "role": "admin"}',
        b'{"login_name": 7, "password": "x"}',
        ('{"login_name": "' + "x" * 65 + '", "password": "x"}').encode(),
        ('{"login_name": "x", "password": "' + "x" * 129 + '"}').encode(),
    ],
)
async def test_invalid_body_returns_invalid_request(backend: RunningBackend, body: bytes) -> None:
    response = await backend.client.post(
        "/v1/sessions", content=body, headers={"Origin": ALLOWED_ORIGIN}
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["type"] == "urn:supportiq:problem:invalid-request"


async def test_password_is_never_repeated_in_a_validation_error(
    backend: RunningBackend,
) -> None:
    response = await backend.client.post(
        "/v1/sessions",
        json={"login_name": "staff-1", "password": "secret-of-the-test", "role": "admin"},
        headers=ORIGIN_HEADERS,
    )

    assert "secret-of-the-test" not in response.text


async def test_unreachable_database_returns_not_ready(worker_database: WorkerDatabase) -> None:
    settings = build_settings(worker_database, database_url_app=UNREACHABLE_URL)
    events = RecordingEventRecorder()

    async with running_client(settings, events, FakeClock()) as client:
        response = await sign_in(client, credentials())

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"
    assert EventName.DATABASE_CALL_FAILED in events.names()


@pytest.mark.usefixtures("account_id")
async def test_sign_in_events_never_carry_the_login_name(backend: RunningBackend) -> None:
    await sign_in(backend.client, credentials())
    await sign_in(backend.client, credentials(password="wrong-test-password"))

    recorded = repr(backend.events.events)

    assert LOGIN_NAME not in recorded
    assert KNOWN_PASSWORD not in recorded
