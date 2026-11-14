"""Health checks, error bodies, traces, and request logs over HTTP (ERR-18, CON-12, LOG-05)."""

import re
from http import HTTPStatus

import pytest

from supportiq_ai_service.platform import EventName
from tests.integration.application import SERVICE_TOKEN_HEADERS, running_ai_service
from tests.unit.release.fakes import FailingReleaseSource, StaticReleaseSource

pytestmark = pytest.mark.anyio

PROBLEM_MEDIA_TYPE = "application/problem+json"
TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
CALLER_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
VALID_TRACEPARENT = f"00-{CALLER_TRACE_ID}-00f067aa0ba902b7-01"


@pytest.mark.parametrize("release_source", [StaticReleaseSource(), StaticReleaseSource(None)])
async def test_liveness_answers_204_without_a_body_or_a_token(
    release_source: StaticReleaseSource,
) -> None:
    async with running_ai_service(release_source) as service:
        response = await service.client.get("/health/live")

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""


async def test_readiness_answers_204_with_a_loaded_release() -> None:
    async with running_ai_service() as service:
        response = await service.client.get("/health/ready")

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""


async def test_readiness_answers_not_ready_without_a_loaded_release() -> None:
    async with running_ai_service(StaticReleaseSource(None)) as service:
        response = await service.client.get("/health/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == "urn:supportiq:problem:not-ready"
    assert body["detail"] == "The release manifest is not loaded."
    assert TRACE_ID_PATTERN.fullmatch(body["trace_id"])
    (refused,) = service.events.of(EventName.REQUEST_REFUSED)
    assert refused.attributes == {"error_type": "ReleaseNotLoadedError"}


async def test_an_unknown_path_is_not_found() -> None:
    async with running_ai_service() as service:
        response = await service.client.get("/v1/unknown", headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["type"] == "urn:supportiq:problem:not-found"


async def test_a_trailing_slash_is_an_unknown_path() -> None:
    async with running_ai_service() as service:
        response = await service.client.get("/health/live/")

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_a_method_that_the_contract_does_not_define_names_the_allowed_ones() -> None:
    async with running_ai_service() as service:
        response = await service.client.post("/health/live")

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["allow"] == "GET"
    assert response.json()["type"] == "urn:supportiq:problem:invalid-request"


async def test_an_unexpected_failure_is_an_internal_error_logged_once() -> None:
    async with running_ai_service(FailingReleaseSource()) as service:
        response = await service.client.get("/v1/asset-versions", headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    body = response.json()
    assert body["type"] == "urn:supportiq:problem:internal-error"
    assert body["detail"] == "An unexpected error occurred."
    assert "release source failed" not in response.text
    (failed,) = service.events.of(EventName.REQUEST_FAILED)
    assert failed.attributes == {"error_type": "RuntimeError"}


async def test_an_error_body_continues_the_trace_of_the_caller() -> None:
    async with running_ai_service(StaticReleaseSource(None)) as service:
        response = await service.client.get(
            "/health/ready", headers={"traceparent": VALID_TRACEPARENT}
        )

    assert response.json()["trace_id"] == CALLER_TRACE_ID


async def test_an_invalid_traceparent_starts_a_new_trace_and_is_no_error() -> None:
    async with running_ai_service(StaticReleaseSource(None)) as service:
        response = await service.client.get(
            "/health/ready", headers={"traceparent": "not-a-traceparent"}
        )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    trace_id = response.json()["trace_id"]
    assert TRACE_ID_PATTERN.fullmatch(trace_id)
    assert trace_id not in {CALLER_TRACE_ID, "0" * 32}


async def test_every_request_is_logged_once_with_its_route_template() -> None:
    async with running_ai_service() as service:
        await service.client.get("/v1/asset-versions", headers=SERVICE_TOKEN_HEADERS)

    (completed,) = service.events.of(EventName.REQUEST_COMPLETED)
    assert completed.attributes == {
        "http_method": "GET",
        "http_status_code": HTTPStatus.OK.value,
        "duration_ms": 0,
        "http_route": "/v1/asset-versions",
    }


async def test_the_lifespan_logs_startup_and_shutdown() -> None:
    async with running_ai_service() as service:
        pass

    assert service.events.names() == (EventName.STARTUP_COMPLETED, EventName.SHUTDOWN_STARTED)
