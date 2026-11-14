"""Every operation except the health checks needs the service token (ADR-0018, Access).

A missing or wrong token is refused with `401 unauthenticated`, before anything else is
checked, and the body never repeats what was sent (SEC-09). The health checks need no token.
"""

from http import HTTPStatus

import pytest

from supportiq_ai_service.platform import EventName
from tests.integration.application import SERVICE_TOKEN, running_ai_service
from tests.unit.release.fakes import StaticReleaseSource

pytestmark = pytest.mark.anyio

# The operations of contract 1.0.0 that ai-service serves so far, other than the health checks.
SECURED_OPERATIONS = (("GET", "/v1/asset-versions"),)
WRONG_AUTHORIZATIONS = (
    None,
    "Bearer wrong-token",
    f"Basic {SERVICE_TOKEN}",
    f"Bearer {SERVICE_TOKEN}-and-more",
)


@pytest.mark.parametrize(("method", "path"), SECURED_OPERATIONS)
@pytest.mark.parametrize("authorization", WRONG_AUTHORIZATIONS)
async def test_an_operation_refuses_a_missing_or_wrong_service_token(
    method: str, path: str, authorization: str | None
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}
    async with running_ai_service() as service:
        response = await service.client.request(method, path, headers=headers)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["type"] == "urn:supportiq:problem:unauthenticated"
    assert SERVICE_TOKEN not in response.text
    assert service.events.of(EventName.SERVICE_TOKEN_REJECTED)


@pytest.mark.parametrize(("method", "path"), SECURED_OPERATIONS)
async def test_the_token_is_checked_before_readiness(method: str, path: str) -> None:
    async with running_ai_service(StaticReleaseSource(None)) as service:
        response = await service.client.request(method, path)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
async def test_the_health_checks_need_no_token(path: str) -> None:
    async with running_ai_service() as service:
        response = await service.client.get(path)

    assert response.status_code == HTTPStatus.NO_CONTENT
