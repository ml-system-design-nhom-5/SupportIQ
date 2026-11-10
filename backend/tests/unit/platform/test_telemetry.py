"""Tests of span redaction: only allow-listed attributes leave the process (LOG-29, LOG-30)."""

from collections.abc import Mapping, Sequence

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from supportiq_backend.platform import SpanName
from supportiq_backend.platform.adapters.telemetry import (
    OpenTelemetryStepTracer,
    OpenTelemetryTraceContext,
    RedactingSpanProcessor,
)

ORDER_PATH = "/v1/shop/orders/ORD-20931"


def record_one_span() -> tuple[Mapping[str, object], Sequence[Mapping[str, object]]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))
    with provider.get_tracer("test").start_as_current_span(
        "GET /v1/shop/orders/{order_id}"
    ) as span:
        span.set_attributes(
            {
                "http.route": "/v1/shop/orders/{order_id}",
                "http.target": ORDER_PATH,
                "url.path": ORDER_PATH,
                "url.query": "cursor=abc",
                "http.url": f"http://localhost{ORDER_PATH}",
                "client.address": "127.0.0.1",
                "http.status_code": 200,
            }
        )
        span.add_event("exception", {"exception.type": "KeyError", "exception.message": ORDER_PATH})
        span.add_event("note", {"order_id": "ORD-20931"})
    (finished,) = exporter.get_finished_spans()
    events = [dict(event.attributes or {}) for event in finished.events]
    return dict(finished.attributes or {}), events


def test_exported_span_keeps_only_allow_listed_attributes() -> None:
    attributes, _ = record_one_span()

    assert attributes == {"http.route": "/v1/shop/orders/{order_id}", "http.status_code": 200}


def test_exported_exception_event_keeps_only_the_error_type() -> None:
    _, events = record_one_span()

    assert events == [{"exception.type": "KeyError"}, {}]


def tracer_provider_with(exporter: InMemorySpanExporter) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))
    return provider


def test_recorded_failure_marks_the_span_and_keeps_only_the_error_type() -> None:
    exporter = InMemorySpanExporter()

    with tracer_provider_with(exporter).get_tracer("test").start_as_current_span("request"):
        OpenTelemetryTraceContext().record_failure(KeyError(ORDER_PATH))

    (span,) = exporter.get_finished_spans()
    (event,) = span.events
    assert span.status.status_code is StatusCode.ERROR
    assert dict(event.attributes or {}) == {"exception.type": "KeyError"}


def test_exported_status_keeps_its_code_and_loses_its_description() -> None:
    exporter = InMemorySpanExporter()

    with (
        tracer_provider_with(exporter).get_tracer("test").start_as_current_span("statement") as (
            span
        )
    ):
        span.set_status(Status(StatusCode.ERROR, f"invalid input: {ORDER_PATH}"))

    (exported,) = exporter.get_finished_spans()
    assert exported.status.status_code is StatusCode.ERROR
    assert exported.status.description is None


def test_step_runs_in_a_span_under_the_current_span() -> None:
    exporter = InMemorySpanExporter()
    provider = tracer_provider_with(exporter)

    with (
        provider.get_tracer("test").start_as_current_span("request"),
        OpenTelemetryStepTracer(provider).step(SpanName.CREATE_TICKET),
    ):
        pass

    (step, request) = exporter.get_finished_spans()
    assert step.name == "create_ticket"
    assert step.parent is not None
    assert request.context is not None
    assert step.parent.span_id == request.context.span_id


def test_step_carries_its_ticket_as_an_attribute_that_leaves_the_process() -> None:
    exporter = InMemorySpanExporter()
    tracer = OpenTelemetryStepTracer(tracer_provider_with(exporter))

    with tracer.step(SpanName.CREATE_TICKET):
        tracer.record_ticket("TCK-1001")

    (step,) = exporter.get_finished_spans()
    assert dict(step.attributes or {}) == {"ticket_id": "TCK-1001"}


def test_exception_that_leaves_a_step_marks_nothing() -> None:
    exporter = InMemorySpanExporter()
    tracer = OpenTelemetryStepTracer(tracer_provider_with(exporter))

    with pytest.raises(KeyError), tracer.step(SpanName.CREATE_TICKET):
        raise KeyError(ORDER_PATH)

    (step,) = exporter.get_finished_spans()
    assert step.status.status_code is StatusCode.UNSET
    assert step.events == ()
