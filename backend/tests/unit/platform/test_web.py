"""Tests of the interface layer of platform: the exception handler and the request log.

The application under test is built here with test routes, so every error path of the single
exception handler is reached without a database (PY-38, ERR-21).
"""

from collections.abc import AsyncGenerator
from http import HTTPStatus
from typing import Annotated

import anyio
import httpx
import pytest
from fastapi import FastAPI, Path, Response
from fastapi.responses import StreamingResponse
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.types import Message, Scope

from supportiq_backend.platform import (
    CheckReadiness,
    DatabaseOperationError,
    DatabaseUnavailableError,
    EventName,
    ResourceNotFoundError,
)
from supportiq_backend.platform.adapters.telemetry import (
    OpenTelemetryTraceContext,
    RedactingSpanProcessor,
    instrument_application,
)
from supportiq_backend.platform.web import (
    PROBLEM_MEDIA_TYPE,
    RequestLoggingMiddleware,
    build_health_router,
    install_exception_handling,
)
from tests.unit.platform.fakes import FakeClock, FakeReadinessProbe, RecordingEventRecorder

pytestmark = pytest.mark.anyio

SECRET_DETAIL = "Key (order_id)=(ORD-20931) already exists"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{TRACE_ID}-00f067aa0ba902b7-01"
REQUEST_THAT_FAILS_AFTER_THE_START: Scope = {
    "type": "http",
    "asgi": {"version": "3.0"},
    "http_version": "1.1",
    "method": "GET",
    "scheme": "http",
    "path": "/v1/failures/after-the-response-started",
    "raw_path": b"/v1/failures/after-the-response-started",
    "query_string": b"",
    "root_path": "",
    "headers": [],
    "server": ("backend.test", 80),
    "client": ("127.0.0.1", 1),
}


def build_app(
    events: RecordingEventRecorder,
    readiness: CheckReadiness,
    tracer_provider: TracerProvider | None = None,
) -> FastAPI:
    app = FastAPI()
    install_exception_handling(app, events, OpenTelemetryTraceContext())
    app.add_middleware(RequestLoggingMiddleware, events=events, clock=FakeClock())
    app.include_router(build_health_router(readiness))

    @app.get("/v1/orders/{order_id}")
    async def handle_get_order(_order_id: Annotated[str, Path(alias="order_id")]) -> Response:
        raise ResourceNotFoundError

    @app.get("/v1/failures/database")
    async def handle_database_defect() -> Response:
        raise DatabaseOperationError from KeyError(SECRET_DETAIL)

    @app.get("/v1/failures/unexpected")
    async def handle_unexpected_failure() -> Response:
        raise RuntimeError(SECRET_DETAIL)

    @app.get("/v1/two-methods")
    async def handle_read_of_a_resource_with_two_methods() -> Response:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    @app.post("/v1/two-methods")
    async def handle_write_of_a_resource_with_two_methods() -> Response:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    @app.get("/v1/numbers/{number}")
    async def handle_get_number(_number: Annotated[int, Path(alias="number")]) -> Response:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    add_route_that_fails_after_the_response_started(app)
    instrument_application(app, tracer_provider or TracerProvider())
    return app


def add_route_that_fails_after_the_response_started(app: FastAPI) -> None:
    async def first_chunk_then_failure() -> AsyncGenerator[bytes]:
        yield b"first chunk"
        raise RuntimeError(SECRET_DETAIL)

    @app.get("/v1/failures/after-the-response-started")
    async def handle_failure_after_the_response_started() -> StreamingResponse:
        return StreamingResponse(first_chunk_then_failure())


@pytest.fixture
def events() -> RecordingEventRecorder:
    return RecordingEventRecorder()


async def send_get(
    events: RecordingEventRecorder,
    path: str,
    *,
    readiness: CheckReadiness | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    app = build_app(events, readiness or CheckReadiness((FakeReadinessProbe(),)))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend.test") as client:
        return await client.get(path, headers=headers)


async def test_domain_error_becomes_its_problem_details_body(
    events: RecordingEventRecorder,
) -> None:
    response = await send_get(events, "/v1/orders/ORD-20931")

    body = response.json()

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert body["type"] == "urn:supportiq:problem:not-found"
    assert body["detail"] == "The resource was not found."


async def test_problem_body_carries_the_trace_id_of_the_incoming_traceparent(
    events: RecordingEventRecorder,
) -> None:
    response = await send_get(events, "/v1/orders/ORD-1", headers={"traceparent": TRACEPARENT})

    assert response.json()["trace_id"] == TRACE_ID


async def test_problem_body_starts_a_new_trace_for_an_invalid_traceparent(
    events: RecordingEventRecorder,
) -> None:
    response = await send_get(events, "/v1/orders/ORD-1", headers={"traceparent": "garbage"})

    trace_id = response.json()["trace_id"]

    assert len(trace_id) == len(TRACE_ID)
    assert trace_id not in {TRACE_ID, "0" * 32}


async def test_unexpected_exception_becomes_internal_error_without_details(
    events: RecordingEventRecorder,
) -> None:
    response = await send_get(events, "/v1/failures/unexpected")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["type"] == "urn:supportiq:problem:internal-error"
    assert response.json()["detail"] == "An unexpected error occurred."
    assert SECRET_DETAIL not in response.text


async def test_unexpected_exception_is_logged_once_with_its_type(
    events: RecordingEventRecorder,
) -> None:
    await send_get(events, "/v1/failures/unexpected")

    (failure,) = events.of(EventName.REQUEST_FAILED)

    assert failure.attributes == {"error_type": "RuntimeError"}


async def test_database_defect_is_logged_with_the_type_of_its_cause(
    events: RecordingEventRecorder,
) -> None:
    response = await send_get(events, "/v1/failures/database")

    (failure,) = events.of(EventName.REQUEST_FAILED)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert failure.attributes == {"error_type": "KeyError"}
    assert SECRET_DETAIL not in response.text


async def test_readiness_answers_204_when_every_dependency_answers(
    events: RecordingEventRecorder,
) -> None:
    response = await send_get(events, "/health/ready")

    assert response.status_code == HTTPStatus.NO_CONTENT


async def test_readiness_answers_503_and_logs_when_the_database_does_not_answer(
    events: RecordingEventRecorder,
) -> None:
    readiness = CheckReadiness((FakeReadinessProbe(DatabaseUnavailableError()),))

    response = await send_get(events, "/health/ready", readiness=readiness)

    (unavailable,) = events.of(EventName.DATABASE_CALL_FAILED)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"
    assert unavailable.attributes == {"error_type": "DatabaseUnavailableError"}


async def test_liveness_answers_204_without_checking_dependencies(
    events: RecordingEventRecorder,
) -> None:
    readiness = CheckReadiness((FakeReadinessProbe(DatabaseUnavailableError()),))

    response = await send_get(events, "/health/live", readiness=readiness)

    assert response.status_code == HTTPStatus.NO_CONTENT


async def test_unknown_path_becomes_a_not_found_problem(events: RecordingEventRecorder) -> None:
    response = await send_get(events, "/v1/unknown")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["type"] == "urn:supportiq:problem:not-found"


async def test_undefined_method_becomes_a_405_problem_with_allow(
    events: RecordingEventRecorder,
) -> None:
    app = build_app(events, CheckReadiness((FakeReadinessProbe(),)))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend.test") as client:
        response = await client.delete("/health/live")

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["allow"] == "GET"
    assert response.json()["type"] == "urn:supportiq:problem:invalid-request"


async def test_framework_validation_error_names_the_location_but_not_the_value(
    events: RecordingEventRecorder,
) -> None:
    response = await send_get(events, "/v1/numbers/Lan-Tran")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == "The request does not match the contract at: path.number."
    assert "Lan-Tran" not in response.text


async def test_request_log_records_the_route_template_and_never_the_raw_path(
    events: RecordingEventRecorder,
) -> None:
    await send_get(events, "/v1/orders/ORD-20931?cursor=secret-cursor")

    (completed,) = events.of(EventName.REQUEST_COMPLETED)

    assert completed.attributes == {
        "http_method": "GET",
        "http_route": "/v1/orders/{order_id}",
        "http_status_code": HTTPStatus.NOT_FOUND,
        "duration_ms": 0,
    }


async def test_request_log_omits_the_route_of_an_unknown_path(
    events: RecordingEventRecorder,
) -> None:
    await send_get(events, "/v1/ORD-20931")

    (completed,) = events.of(EventName.REQUEST_COMPLETED)

    assert "http_route" not in completed.attributes


async def test_allow_lists_every_method_of_a_path_with_one_route_per_method(
    events: RecordingEventRecorder,
) -> None:
    app = build_app(events, CheckReadiness((FakeReadinessProbe(),)))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/v1/two-methods")

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["allow"] == "GET, POST"


async def test_allow_covers_a_route_of_an_included_router(events: RecordingEventRecorder) -> None:
    app = build_app(events, CheckReadiness((FakeReadinessProbe(),)))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/health/live")

    assert response.headers["allow"] == "GET"


async def spans_of_get(
    events: RecordingEventRecorder, path: str, readiness: CheckReadiness
) -> tuple[ReadableSpan, ...]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))
    transport = httpx.ASGITransport(
        app=build_app(events, readiness, provider), raise_app_exceptions=False
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://backend.test") as client:
        await client.get(path)
    return tuple(exporter.get_finished_spans())


def exception_types_of(spans: tuple[ReadableSpan, ...]) -> list[str]:
    return [
        str((event.attributes or {}).get("exception.type")).rsplit(".", 1)[-1]
        for span in spans
        for event in span.events
        if event.name == "exception"
    ]


async def test_unexpected_failure_is_recorded_on_the_span_of_the_request(
    events: RecordingEventRecorder,
) -> None:
    spans = await spans_of_get(
        events, "/v1/failures/unexpected", CheckReadiness((FakeReadinessProbe(),))
    )

    assert exception_types_of(spans) == ["RuntimeError"]
    assert SECRET_DETAIL not in repr([span.to_json() for span in spans])


async def test_unavailable_database_is_recorded_on_the_span_of_the_request(
    events: RecordingEventRecorder,
) -> None:
    readiness = CheckReadiness((FakeReadinessProbe(DatabaseUnavailableError()),))

    spans = await spans_of_get(events, "/health/ready", readiness)

    assert exception_types_of(spans) == ["DatabaseUnavailableError"]


async def test_refusal_is_not_recorded_as_a_failure(events: RecordingEventRecorder) -> None:
    spans = await spans_of_get(events, "/v1/orders/ORD-1", CheckReadiness((FakeReadinessProbe(),)))

    assert exception_types_of(spans) == []


async def test_failure_after_the_response_started_is_recorded_and_sends_no_second_response(
    events: RecordingEventRecorder,
) -> None:
    app = build_app(events, CheckReadiness((FakeReadinessProbe(),)))
    sent: list[Message] = []

    async def wait_for_ever() -> Message:
        await anyio.sleep_forever()
        return {}

    async def keep(message: Message) -> None:
        sent.append(message)

    await app(REQUEST_THAT_FAILS_AFTER_THE_START, wait_for_ever, keep)

    (failed,) = events.of(EventName.REQUEST_FAILED)
    assert [message["type"] for message in sent].count("http.response.start") == 1
    assert failed.attributes == {"error_type": "RuntimeError"}
