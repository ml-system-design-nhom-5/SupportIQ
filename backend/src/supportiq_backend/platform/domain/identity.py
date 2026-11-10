"""Ports for generated identifiers and for the trace of the current work (ARCH-31, LOG-04)."""

from contextlib import AbstractContextManager
from enum import StrEnum
from typing import NewType, Protocol
from uuid import UUID

# A W3C trace ID as 32 lowercase hexadecimal characters. Internal data.
TraceId = NewType("TraceId", str)
TRACE_ID_FORMAT = "032x"


class SpanName(StrEnum):
    """The steps of backend that have a span of their own (LOG-20)."""

    CREATE_TICKET = "create_ticket"


class IdGenerator(Protocol):
    """Generate unique identifiers, so tests can replace them with predictable ones."""

    def generate(self) -> UUID:
        """Return a new identifier that no earlier call returned."""
        ...


class TraceContext(Protocol):
    """Tell the trace of the work in progress: the request, or a command."""

    def current_trace_id(self) -> TraceId:
        """Return the trace ID of the current span.

        Returns:
            The trace ID, as 32 lowercase hexadecimal characters.
        """
        ...

    def record_failure(self, error: BaseException) -> None:
        """Mark the current span as failed, with an exception event (LOG-22).

        Args:
            error: What failed. Only its type leaves the process.
        """
        ...


class StepTracer(Protocol):
    """Run one step of work in a span of its own."""

    def step(self, name: SpanName) -> AbstractContextManager[None]:
        """Open the span of a step.

        Args:
            name: The step.

        Returns:
            The context that holds the span. An exception that leaves it marks nothing: an
            expected refusal is no failure, and the exception handler records real ones.
        """
        ...

    def record_ticket(self, ticket_id: str) -> None:
        """Name the ticket of the current step, so a trace is found by its ID (LOG-07).

        Args:
            ticket_id: The ticket, an Internal identifier.
        """
        ...
