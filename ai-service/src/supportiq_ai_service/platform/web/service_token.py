"""The service token check of every operation except the health checks (ADR-0018, Access).

`backend` sends `Authorization: Bearer <service token>`. The scheme is case-insensitive
(RFC 9110, section 11.1), the token is compared in constant time, and a missing or wrong
token becomes `401 unauthenticated` without repeating what was sent (SEC-09).
"""

import hmac
from collections.abc import Callable

from fastapi import Request

from supportiq_ai_service.platform import ServiceTokenRejectedError

AUTHORIZATION_HEADER = "authorization"
_BEARER_SCHEME = "bearer"
_HEADER_ENCODING = "utf-8"


def build_service_token_guard(service_token: str) -> Callable[[Request], None]:
    """Build the FastAPI dependency that admits only requests with the service token.

    Args:
        service_token: The secret value of the setting `service_token`.

    Returns:
        The dependency, for the `dependencies` of every router except the health checks.
    """
    expected = service_token.encode(_HEADER_ENCODING)

    def require_service_token(request: Request) -> None:
        if not _matches(request.headers.get(AUTHORIZATION_HEADER), expected):
            raise ServiceTokenRejectedError

    return require_service_token


def _matches(authorization: str | None, expected: bytes) -> bool:
    if authorization is None:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != _BEARER_SCHEME or not token:
        return False
    return hmac.compare_digest(token.encode(_HEADER_ENCODING), expected)
