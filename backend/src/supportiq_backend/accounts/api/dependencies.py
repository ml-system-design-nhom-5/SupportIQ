"""The request dependencies that every router uses: `Origin` check and session (ADR-0009).

FastAPI runs the dependencies of a route in order, before the handler reads the body, so the
`Origin` check of a state-changing route runs before authentication, before validation, and
before anything else (ADR-0009, statement 7; contract, Authentication and roles).
"""

from fastapi import Request

from supportiq_backend.accounts.domain import (
    AuthenticatedSession,
    Authenticator,
    OriginPolicy,
    SessionToken,
    validate_origin,
)
from supportiq_backend.platform.web import RequestDependency

SESSION_COOKIE_NAME = "supportiq_session"
ORIGIN_HEADER = "origin"

type OriginCheck = RequestDependency[None]
type CurrentSession = RequestDependency[AuthenticatedSession]


def build_origin_check(policy: OriginPolicy) -> OriginCheck:
    """Build the dependency that refuses a request without an allowed `Origin`.

    Args:
        policy: The origin policy.

    Returns:
        The dependency function, for the `dependencies` of a state-changing route.
    """

    async def check_origin(request: Request) -> None:
        validate_origin(request.headers.get(ORIGIN_HEADER), policy)

    return check_origin


def build_current_session(authenticator: Authenticator) -> CurrentSession:
    """Build the dependency that turns the session cookie into a valid session.

    Args:
        authenticator: The authentication port.

    Returns:
        The dependency function, which raises `SessionRequiredError` without a valid session.
    """

    async def current_session(request: Request) -> AuthenticatedSession:
        cookie = request.cookies.get(SESSION_COOKIE_NAME)
        return await authenticator.authenticate(None if cookie is None else SessionToken(cookie))

    return current_session
