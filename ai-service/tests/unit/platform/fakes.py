"""In-memory fakes of the platform ports: clock, events, and trace context (ARCH-27)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from supportiq_ai_service.platform import EventAttributeValue, EventName, TraceId

FAKE_CLOCK_START = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
FAKE_TRACE_ID = TraceId("4bf92f3577b34da6a3ce929d0e0e4736")


class FakeClock:
    """A clock that only moves when a test moves it, so no test waits (TEST-14)."""

    def __init__(self, start: datetime = FAKE_CLOCK_START) -> None:
        """Start the clock.

        Args:
            start: The first time that `now` returns.
        """
        self._now = start

    def now(self) -> datetime:
        """Return the current fake time."""
        return self._now

    def advance(self, duration_ms: int) -> None:
        """Move the time forward.

        Args:
            duration_ms: How far, in milliseconds.
        """
        self._now += timedelta(milliseconds=duration_ms)


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """One recorded event.

    Attributes:
        name: The event.
        attributes: Its attributes.
    """

    name: EventName
    attributes: Mapping[str, EventAttributeValue]


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

    def names(self) -> tuple[EventName, ...]:
        """Return the names of the recorded events, in order."""
        return tuple(recorded.name for recorded in self.events)

    def of(self, name: EventName) -> tuple[RecordedEvent, ...]:
        """Return the recorded events with one name, in order.

        Args:
            name: The event to select.
        """
        return tuple(recorded for recorded in self.events if recorded.name is name)


@dataclass(frozen=True, slots=True)
class FixedTraceContext:
    """A trace context that always names the same trace."""

    trace_id: TraceId = FAKE_TRACE_ID

    def current_trace_id(self) -> TraceId:
        """Return the fixed trace ID."""
        return self.trace_id
