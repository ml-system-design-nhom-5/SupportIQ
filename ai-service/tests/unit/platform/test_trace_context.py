"""A valid `traceparent` continues the trace; otherwise a new trace starts (LOG-05)."""

import re

import pytest
from opentelemetry import context, trace

from supportiq_ai_service.platform.adapters.trace_context import (
    NO_TRACE_ID,
    OpenTelemetryTraceContext,
    request_context,
)

CALLER_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
CALLER_SPAN_ID = "00f067aa0ba902b7"
VALID_TRACEPARENT = f"00-{CALLER_TRACE_ID}-{CALLER_SPAN_ID}-01"
TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def trace_and_span_of(headers: dict[str, str]) -> tuple[str, str]:
    span_context = trace.get_current_span(request_context(headers)).get_span_context()
    return format(span_context.trace_id, "032x"), format(span_context.span_id, "016x")


def test_a_valid_traceparent_continues_the_trace_with_a_new_span() -> None:
    trace_id, span_id = trace_and_span_of({"traceparent": VALID_TRACEPARENT})

    assert trace_id == CALLER_TRACE_ID
    assert span_id not in {CALLER_SPAN_ID, "0" * 16}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"traceparent": "not-a-traceparent"},
        {"traceparent": f"00-{'0' * 32}-{CALLER_SPAN_ID}-01"},
        {"traceparent": f"00-{CALLER_TRACE_ID}-{'0' * 16}-01"},
    ],
)
def test_an_absent_or_invalid_traceparent_starts_a_new_trace(headers: dict[str, str]) -> None:
    trace_id, span_id = trace_and_span_of(headers)

    assert TRACE_ID_PATTERN.fullmatch(trace_id)
    assert trace_id not in {CALLER_TRACE_ID, NO_TRACE_ID}
    assert span_id != "0" * 16


def test_two_requests_without_traceparent_get_two_traces() -> None:
    first, _ = trace_and_span_of({})
    second, _ = trace_and_span_of({})

    assert first != second


def test_the_trace_context_names_the_trace_of_the_current_request() -> None:
    token = context.attach(request_context({"traceparent": VALID_TRACEPARENT}))
    try:
        assert OpenTelemetryTraceContext().current_trace_id() == CALLER_TRACE_ID
    finally:
        context.detach(token)


def test_outside_a_request_the_trace_context_names_no_trace() -> None:
    assert OpenTelemetryTraceContext().current_trace_id() == NO_TRACE_ID
