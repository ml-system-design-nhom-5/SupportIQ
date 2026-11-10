"""The session dependency of every router, with a fake of the `Authenticator` port (ARCH-27)."""

import pytest
from starlette.requests import Request

from supportiq_backend.accounts import (
    AuthenticatedSession,
    InternalPrincipal,
    InternalRole,
    SessionRequiredError,
    SessionToken,
)
from supportiq_backend.accounts.api.dependencies import SESSION_COOKIE_NAME, build_current_session
from supportiq_backend.platform import DatabaseUnavailableError
from tests.unit.accounts.fakes import (
    DEFAULT_SESSION_ID_HASH,
    FakeAuthenticator,
    build_session_account,
)

pytestmark = pytest.mark.anyio

TOKEN = "a-session-identifier"
ACCOUNT = build_session_account()
PRINCIPAL = InternalPrincipal(ACCOUNT.account_id, InternalRole.STAFF)


def request_with_cookie(cookie: bytes | None) -> Request:
    headers = [] if cookie is None else [(b"cookie", cookie)]
    return Request({"type": "http", "headers": headers})


async def test_cookie_reaches_the_authenticator_and_its_session_comes_back() -> None:
    session = AuthenticatedSession(DEFAULT_SESSION_ID_HASH, PRINCIPAL, ACCOUNT)
    authenticator = FakeAuthenticator(session)
    request = request_with_cookie(f"{SESSION_COOKIE_NAME}={TOKEN}".encode())

    result = await build_current_session(authenticator)(request)

    assert result == session
    assert authenticator.tokens == [SessionToken(TOKEN)]


async def test_request_without_the_cookie_reaches_the_authenticator_as_none() -> None:
    authenticator = FakeAuthenticator()

    with pytest.raises(SessionRequiredError):
        await build_current_session(authenticator)(request_with_cookie(None))

    assert authenticator.tokens == [None]


async def test_failure_of_the_authenticator_reaches_the_caller() -> None:
    authenticator = FakeAuthenticator(failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await build_current_session(authenticator)(request_with_cookie(None))
