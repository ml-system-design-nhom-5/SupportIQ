"""The trace setup of backend: tracer provider, exporter, instrumentation, redaction (ADR-0007).

Spans are created even when nothing is exported, so every request has a trace ID for its
Problem Details bodies (LOG-04). Before a finished span reaches the exporter, every attribute
that is not allow-listed is dropped, exception events keep only the error type, and a status
keeps only its code. The
FastAPI instrumentation records the raw path and query, which can hold an order ID, so those
attributes never leave the process; the route template does (backend foundation design,
Errors and guardrails).
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    Status,
    StatusCode,
    TraceFlags,
)
from opentelemetry.util.types import AttributeValue
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.platform.domain import (
    MILLISECONDS_PER_SECOND,
    SERVICE_NAME,
    TRACE_ID_FORMAT,
    SpanName,
    TraceId,
)

EXCEPTION_EVENT_NAME = "exception"
TICKET_ID_ATTRIBUTE = "ticket_id"
PSEUDONYM_COUNT_ATTRIBUTE = "pseudonym_count"
AI_SERVICE_OPERATION_ATTRIBUTE = "ai_service_operation"
# The trace ID of work without a span. The composition root starts a span for every request
# and every command, so a record carries it only when tracing was not set up.
NO_TRACE_ID = TraceId("0" * 32)
# The span attributes that may leave the process. The FastAPI, ASGI, and SQLAlchemy
# instrumentations set others too, such as `http.target`, `http.url`, `url.path`, `url.query`,
# `client.address`, and `user_agent.original`, which are dropped (LOG-29).
ALLOWED_SPAN_ATTRIBUTES = frozenset(
    {
        "http.method",
        "http.request.method",
        "http.route",
        "http.status_code",
        "http.response.status_code",
        "http.scheme",
        "url.scheme",
        "http.flavor",
        "network.protocol.version",
        "db.system",
        "db.system.name",
        "db.name",
        "db.namespace",
        "db.user",
        "db.statement",
        "db.query.text",
        "db.operation.name",
        "net.peer.name",
        "net.peer.port",
        "server.address",
        "server.port",
        "error.type",
        TICKET_ID_ATTRIBUTE,
        PSEUDONYM_COUNT_ATTRIBUTE,
        AI_SERVICE_OPERATION_ATTRIBUTE,
    }
)
ALLOWED_EXCEPTION_ATTRIBUTES = frozenset({"exception.type"})
_NO_NAMES: frozenset[str] = frozenset()
_STEP_TRACER_NAME = "supportiq_backend.steps"
_HEXADECIMAL_BASE = 16


class OpenTelemetryTraceContext:
    """Implement the `TraceContext` port with the current OpenTelemetry span."""

    def current_trace_id(self) -> TraceId:
        """Return the trace ID of the current span, started or continued (LOG-04, LOG-05)."""
        span_context = trace.get_current_span().get_span_context()
        if not span_context.is_valid:
            return NO_TRACE_ID
        return TraceId(format(span_context.trace_id, TRACE_ID_FORMAT))

    def record_failure(self, error: BaseException) -> None:
        """Mark the current span as failed, with an exception event (LOG-22).

        Args:
            error: What failed. `RedactingSpanProcessor` keeps only its type.
        """
        span = trace.get_current_span()
        span.set_status(Status(StatusCode.ERROR))
        span.record_exception(error)


class OpenTelemetryStepTracer:
    """Implement the `StepTracer` port with the tracer provider of the process."""

    def __init__(self, tracer_provider: TracerProvider) -> None:
        """Create the tracer.

        Args:
            tracer_provider: The tracer provider of the process.
        """
        self._tracer = tracer_provider.get_tracer(_STEP_TRACER_NAME)
        self._span_ids = RandomIdGenerator()

    @contextmanager
    def step(self, name: SpanName) -> Generator[None]:
        """Run a step in a span of its own, under the current span (LOG-20).

        Args:
            name: The step.

        Yields:
            Nothing. An exception leaves the span unmarked: an expected refusal is no failure,
            and the exception handler records real failures on the span of the request.
        """
        with self._tracer.start_as_current_span(
            name.value, record_exception=False, set_status_on_exception=False
        ):
            yield

    @contextmanager
    def background_step(self, name: SpanName, trace_id: TraceId) -> Generator[None]:
        """Open the root span of work outside a request, in the trace that queued it (LOG-06).

        Args:
            name: The step.
            trace_id: The trace to join, as 32 hexadecimal characters.

        Yields:
            Nothing. An exception leaves the span unmarked, as in `step`.
        """
        parent = NonRecordingSpan(
            SpanContext(
                trace_id=int(trace_id, _HEXADECIMAL_BASE),
                span_id=self._span_ids.generate_span_id(),
                is_remote=True,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
        )
        with self._tracer.start_as_current_span(
            name.value,
            context=trace.set_span_in_context(parent),
            record_exception=False,
            set_status_on_exception=False,
        ):
            yield

    def record_ticket(self, ticket_id: str) -> None:
        """Name the ticket of the current step, so a trace is found by its ID (LOG-07).

        Args:
            ticket_id: The ticket, an Internal identifier.
        """
        trace.get_current_span().set_attribute(TICKET_ID_ATTRIBUTE, ticket_id)

    def record_pseudonym_count(self, count: int) -> None:
        """Record how many pseudonyms the current step wrote, never their values (LOG-29).

        Args:
            count: The number of distinct pseudonyms.
        """
        trace.get_current_span().set_attribute(PSEUDONYM_COUNT_ATTRIBUTE, count)

    def record_ai_service_endpoint(self, endpoint: str) -> None:
        """Name the `ai-service` operation that the current step calls.

        Args:
            endpoint: The operation ID, such as `createDraft`.
        """
        trace.get_current_span().set_attribute(AI_SERVICE_OPERATION_ATTRIBUTE, endpoint)


class RedactingSpanProcessor(SpanProcessor):
    """Pass finished spans on with only the allow-listed attributes (LOG-29, LOG-30)."""

    def __init__(self, inner: SpanProcessor) -> None:
        """Wrap the processor that exports the spans.

        Args:
            inner: The processor that receives the redacted spans.
        """
        self._inner = inner

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        """Pass the started span on unchanged; nothing leaves the process at start.

        Args:
            span: The started span.
            parent_context: The parent context of the span.
        """
        self._inner.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        """Pass a copy of the finished span with only the allow-listed attributes.

        Args:
            span: The finished span.
        """
        self._inner.on_end(redact_span(span))

    def shutdown(self) -> None:
        """Shut the inner processor down."""
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """Flush the inner processor.

        Args:
            timeout_millis: The longest wait, in milliseconds.

        Returns:
            Whether every span was flushed in time.
        """
        return self._inner.force_flush(timeout_millis)


def redact_span(span: ReadableSpan) -> ReadableSpan:
    """Return a copy of the span with only the allow-listed attributes and event attributes.

    Args:
        span: A finished span.

    Returns:
        The copy that may leave the process.
    """
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=_select(span.attributes, ALLOWED_SPAN_ATTRIBUTES),
        events=tuple(_redact_event(event) for event in span.events),
        links=span.links,
        kind=span.kind,
        # Only the code: the instrumentations copy the error message into the description, and
        # a driver error can repeat a bound value (LOG-29).
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def create_otlp_span_exporter(endpoint: str, *, timeout_ms: int) -> SpanExporter:
    """Create the OTLP/HTTP exporter of finished spans.

    Args:
        endpoint: The traces endpoint of the collector, such as `http://collector:4318/v1/traces`.
        timeout_ms: The longest wait for one export (ERR-09).

    Returns:
        The exporter.
    """
    return OTLPSpanExporter(endpoint=endpoint, timeout=timeout_ms / MILLISECONDS_PER_SECOND)


def create_tracer_provider(exporter: SpanExporter | None) -> TracerProvider:
    """Create the tracer provider of the process; it is never installed as a global.

    Args:
        exporter: Where finished spans go, or None to keep them in the process.

    Returns:
        The provider. The composition root shuts it down at shutdown, which flushes it.
    """
    provider = TracerProvider(
        sampler=ParentBased(ALWAYS_ON),
        resource=Resource({"service.name": SERVICE_NAME}),
    )
    if exporter is not None:
        provider.add_span_processor(RedactingSpanProcessor(BatchSpanProcessor(exporter)))
    return provider


def instrument_application(app: FastAPI, tracer_provider: TracerProvider) -> None:
    """Start a server span for every request, continuing a valid `traceparent` (LOG-05).

    Args:
        app: The application.
        tracer_provider: The provider of the process.
    """
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=tracer_provider, exclude_spans=["receive", "send"]
    )


def instrument_engine(engine: AsyncEngine, tracer_provider: TracerProvider) -> None:
    """Add a span for every statement of the engine (ADR-0007, statement 1).

    Args:
        engine: The engine to instrument.
        tracer_provider: The provider of the process.
    """
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine, tracer_provider=tracer_provider, enable_commenter=False
    )


def uninstrument_engines() -> None:
    """Remove the statement spans at shutdown, so a later start can instrument again."""
    SQLAlchemyInstrumentor().uninstrument()


def _select(
    attributes: Mapping[str, AttributeValue] | None, allowed: frozenset[str]
) -> dict[str, AttributeValue]:
    if attributes is None:
        return {}
    return {name: value for name, value in attributes.items() if name in allowed}


def _redact_event(event: Event) -> Event:
    allowed = ALLOWED_EXCEPTION_ATTRIBUTES if event.name == EXCEPTION_EVENT_NAME else _NO_NAMES
    return Event(
        name=event.name,
        attributes=_select(event.attributes, allowed),
        timestamp=event.timestamp,
    )
