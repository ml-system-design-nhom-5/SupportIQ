"""In-memory fakes of the platform ports: clock, events, readiness, transactions (ARCH-27)."""

from collections.abc import AsyncGenerator, Generator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.platform import (
    BackendError,
    EventAttributeValue,
    EventName,
    SpanName,
    TraceId,
    Transaction,
)

FAKE_CLOCK_START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


class FakeClock:
    """A clock that only moves when a test or a wait moves it, so no test waits (TEST-14)."""

    def __init__(self, start: datetime = FAKE_CLOCK_START) -> None:
        """Start the clock.

        Args:
            start: The first time that `now` returns.
        """
        self._now = start
        self.sleeps_ms: list[int] = []

    def now(self) -> datetime:
        """Return the current fake time."""
        return self._now

    async def sleep(self, duration_ms: int) -> None:
        """Record the wait and move the time forward by it, without waiting.

        Args:
            duration_ms: The duration of the wait, in milliseconds.
        """
        self.sleeps_ms.append(duration_ms)
        self.advance(duration_ms)

    def advance(self, duration_ms: int) -> None:
        """Move the time forward.

        Args:
            duration_ms: How far, in milliseconds.
        """
        self._now += timedelta(milliseconds=duration_ms)


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """One event that a use case recorded.

    Attributes:
        name: The event.
        attributes: Its attributes.
        is_handled_input: Whether it was recorded as caused by handled input.
    """

    name: EventName
    attributes: Mapping[str, EventAttributeValue]
    is_handled_input: bool = False


@dataclass(slots=True)
class RecordingEventRecorder:
    """Keep every recorded event in order, for assertions on emitted events (TEST-06)."""

    events: list[RecordedEvent] = field(default_factory=list[RecordedEvent])

    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Keep the event.

        Args:
            event: The event.
            **attributes: Its attributes.
        """
        self.events.append(RecordedEvent(event, dict(attributes)))

    def record_handled_input(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Keep the event and that handled input caused it.

        Args:
            event: The event.
            **attributes: Its attributes.
        """
        self.events.append(RecordedEvent(event, dict(attributes), is_handled_input=True))

    def names(self) -> tuple[EventName, ...]:
        """Return the names of the recorded events, in order."""
        return tuple(recorded.name for recorded in self.events)

    def of(self, name: EventName) -> tuple[RecordedEvent, ...]:
        """Return the recorded events with one name, in order.

        Args:
            name: The event to select.
        """
        return tuple(recorded for recorded in self.events if recorded.name is name)


FAKE_TRACE_ID = TraceId("4bf92f3577b34da6a3ce929d0e0e4736")


class SequentialIdGenerator:
    """Generate UUIDs from a counter, so tests know every ID in advance (TEST-14)."""

    def __init__(self, start: int = 1) -> None:
        """Start the counter.

        Args:
            start: The number of the first UUID.
        """
        self._next = start

    def generate(self) -> UUID:
        """Return the UUID of the next number."""
        identifier = UUID(int=self._next)
        self._next += 1
        return identifier


@dataclass(frozen=True, slots=True)
class FixedTraceContext:
    """A trace context that always names the same trace and keeps the recorded failures."""

    trace_id: TraceId = FAKE_TRACE_ID
    failures: list[BaseException] = field(default_factory=list[BaseException])

    def current_trace_id(self) -> TraceId:
        """Return the fixed trace ID."""
        return self.trace_id

    def record_failure(self, error: BaseException) -> None:
        """Keep the failure.

        Args:
            error: What failed.
        """
        self.failures.append(error)


@dataclass(slots=True)
class RecordingStepTracer:
    """Keep the steps that a use case ran."""

    steps: list[SpanName] = field(default_factory=list[SpanName])
    tickets: list[str] = field(default_factory=list[str])
    joined_traces: list[TraceId] = field(default_factory=list[TraceId])
    pseudonym_counts: list[int] = field(default_factory=list[int])
    ai_service_endpoints: list[str] = field(default_factory=list[str])

    @contextmanager
    def step(self, name: SpanName) -> Generator[None]:
        """Keep the step.

        Args:
            name: The step.

        Yields:
            Nothing.
        """
        self.steps.append(name)
        yield

    @contextmanager
    def background_step(self, name: SpanName, trace_id: TraceId) -> Generator[None]:
        """Keep the step and the trace it joins.

        Args:
            name: The step.
            trace_id: The trace.

        Yields:
            Nothing.
        """
        self.steps.append(name)
        self.joined_traces.append(trace_id)
        yield

    def record_ticket(self, ticket_id: str) -> None:
        """Keep the ticket of the step.

        Args:
            ticket_id: The ticket.
        """
        self.tickets.append(ticket_id)

    def record_pseudonym_count(self, count: int) -> None:
        """Keep the number of pseudonyms of the step.

        Args:
            count: The number.
        """
        self.pseudonym_counts.append(count)

    def record_ai_service_endpoint(self, endpoint: str) -> None:
        """Keep the `ai-service` operation of the step.

        Args:
            endpoint: The operation ID.
        """
        self.ai_service_endpoints.append(endpoint)


class FakeReadinessProbe:
    """A readiness probe that succeeds, or fails with a given error."""

    def __init__(self, failure: BackendError | None = None) -> None:
        """Choose the outcome.

        Args:
            failure: The error that `check` raises, or None to succeed.
        """
        self._failure = failure
        self.check_count = 0

    async def check(self) -> None:
        """Count the check and raise the chosen failure, if any."""
        self.check_count += 1
        if self._failure is not None:
            raise self._failure


class FakeTransaction[StoresT]:
    """A transaction over in-memory stores that remembers whether it was committed."""

    def __init__(self, stores: StoresT, commit_failure: BackendError | None) -> None:
        """Bind the stores.

        Args:
            stores: The in-memory stores.
            commit_failure: The error that `commit` raises, or None to succeed.
        """
        self._stores = stores
        self._commit_failure = commit_failure
        self.is_committed = False

    @property
    def stores(self) -> StoresT:
        """Return the in-memory stores."""
        return self._stores

    async def commit(self) -> None:
        """Mark the transaction committed, or raise the chosen failure."""
        if self._commit_failure is not None:
            raise self._commit_failure
        self.is_committed = True


class FakeTransactionRunner[StoresT]:
    """Count committed and rolled-back transactions over in-memory stores."""

    def __init__(
        self,
        stores: StoresT,
        *,
        begin_failure: BackendError | None = None,
        commit_failure: BackendError | None = None,
    ) -> None:
        """Keep the stores and the failures to simulate.

        Args:
            stores: The in-memory stores that every transaction sees.
            begin_failure: The error that `begin` raises, or None.
            commit_failure: The error that `commit` raises, or None.
        """
        self._stores = stores
        self._begin_failure = begin_failure
        self._commit_failure = commit_failure
        self.commit_count = 0
        self.rollback_count = 0

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[Transaction[StoresT]]:
        """Open a fake transaction; leaving it without `commit` counts as a rollback.

        Yields:
            The fake transaction.

        Raises:
            BackendError: The chosen `begin_failure`.
        """
        if self._begin_failure is not None:
            raise self._begin_failure
        transaction = FakeTransaction(self._stores, self._commit_failure)
        try:
            yield transaction
        finally:
            if transaction.is_committed:
                self.commit_count += 1
            else:
                self.rollback_count += 1
