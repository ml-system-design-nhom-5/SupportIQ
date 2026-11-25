"""The ports that every feature uses, created once per process (ARCH-21, ARCH-22)."""

from dataclasses import dataclass

from opentelemetry.sdk.trace import TracerProvider

from app.idempotency import IdempotencyGuard
from app.platform import (
    Clock,
    EventRecorder,
    IdGenerator,
    StepTracer,
    TraceContext,
)
from app.platform.adapters.system_ids import RandomIdGenerator
from app.platform.adapters.telemetry import (
    OpenTelemetryStepTracer,
    OpenTelemetryTraceContext,
)
from app.platform.settings import Settings


@dataclass(frozen=True, slots=True)
class SharedPorts:
    """The ports that every feature uses.

    Attributes:
        clock: The clock of the process.
        events: Where events are recorded.
        ids: Generates the IDs of new records.
        traces: Tells the trace of the work in progress.
        steps: Runs a step of work in a span of its own.
        guard: The idempotency guard of retryable writes.
    """

    clock: Clock
    events: EventRecorder
    ids: IdGenerator
    traces: TraceContext
    steps: StepTracer
    guard: IdempotencyGuard


def build_shared_ports(
    settings: Settings,
    events: EventRecorder,
    clock: Clock,
    tracer_provider: TracerProvider,
) -> SharedPorts:
    """Create the shared ports.

    Args:
        settings: The validated settings.
        events: Where events are recorded.
        clock: The clock of the process.
        tracer_provider: The tracer provider of the process.

    Returns:
        The shared ports.
    """
    return SharedPorts(
        clock=clock,
        events=events,
        ids=RandomIdGenerator(),
        traces=OpenTelemetryTraceContext(),
        steps=OpenTelemetryStepTracer(tracer_provider),
        guard=IdempotencyGuard(clock, settings.idempotency_retention_ms),
    )
