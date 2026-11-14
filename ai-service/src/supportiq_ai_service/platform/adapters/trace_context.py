"""The trace of each request: `traceparent` continued or a new trace started (LOG-04, LOG-05).

ai-service uses only the OpenTelemetry API, without an SDK or an exporter, because a
telemetry destination needs a change of ADR-0010 first (ADR-0018, Follow-ups). The middleware
reads `traceparent` with the W3C propagator of the API. A valid header continues the trace of
the caller; an absent or invalid one starts a new trace, as the W3C specification requires,
so the header never causes `422`. Each request gets a span ID of its own, and the trace ID
reaches every error body and every log line of the request.
"""

import secrets

from opentelemetry import context, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Receive, Scope, Send

from supportiq_ai_service.platform.domain import TRACE_ID_FORMAT, TraceId

# The trace ID of work outside every request. The middleware gives each request a trace, so
# a body carries it only when the middleware is not installed: a defect.
NO_TRACE_ID = TraceId("0" * 32)
_TRACE_ID_BITS = 128
_SPAN_ID_BITS = 64
_HEADER_ENCODING = "latin-1"
_PROPAGATOR = TraceContextTextMapPropagator()


class OpenTelemetryTraceContext:
    """Implement the `TraceContext` port with the current OpenTelemetry span context."""

    def current_trace_id(self) -> TraceId:
        """Return the trace ID of the current request, continued or started (LOG-04)."""
        span_context = trace.get_current_span().get_span_context()
        if not span_context.is_valid:
            return NO_TRACE_ID
        return TraceId(format(span_context.trace_id, TRACE_ID_FORMAT))


class TraceContextMiddleware:
    """Give every HTTP request the span context that continues or starts its trace."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the application.

        Args:
            app: The inner application.
        """
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the request inside its span context.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        token = context.attach(request_context(_headers_of(scope)))
        try:
            await self._app(scope, receive, send)
        finally:
            context.detach(token)


def request_context(headers: dict[str, str]) -> context.Context:
    """Return the context of one request: the caller's trace, or a new trace.

    Args:
        headers: The request headers, with lowercase names.

    Returns:
        The context whose current span names the trace ID and a new span ID.
    """
    extracted = _PROPAGATOR.extract(headers)
    parent = trace.get_current_span(extracted).get_span_context()
    if parent.is_valid:
        trace_id, flags = parent.trace_id, parent.trace_flags
    else:
        trace_id, flags = _random_nonzero(_TRACE_ID_BITS), TraceFlags(TraceFlags.SAMPLED)
    span_context = SpanContext(
        trace_id=trace_id,
        span_id=_random_nonzero(_SPAN_ID_BITS),
        is_remote=False,
        trace_flags=flags,
    )
    return trace.set_span_in_context(NonRecordingSpan(span_context), extracted)


def _headers_of(scope: Scope) -> dict[str, str]:
    raw_headers: list[tuple[bytes, bytes]] = scope["headers"]
    return {
        name.decode(_HEADER_ENCODING): value.decode(_HEADER_ENCODING) for name, value in raw_headers
    }


def _random_nonzero(bits: int) -> int:
    # The W3C specification forbids an all-zero trace ID or span ID.
    value = 0
    while value == 0:
        value = secrets.randbits(bits)
    return value
