"""In-memory fakes of platform: clock, events, trace context, and the network (ARCH-27)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from types import MappingProxyType

import httpx

from supportiq_ai_service.platform import EventAttributeValue, EventName, TraceId
from supportiq_ai_service.platform.adapters.egress import EgressAllowList, create_egress_client

FAKE_CLOCK_START = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
FAKE_TRACE_ID = TraceId("4bf92f3577b34da6a3ce929d0e0e4736")
# Test values of the settings of the LLM call, by environment variable (TEST-18). The key calls
# nothing, and the prices are fixtures, never the prices of the provider.
LLM_ENVIRONMENT: Mapping[str, str] = MappingProxyType(
    {
        "GEMINI_API_KEY": "gemini-key-for-tests",
        "GEMINI_MODEL": "gemini-3.5-flash-lite",
        "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "1000",
        "LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "2000",
    }
)


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


class RecordingNetwork(httpx.BaseTransport):
    """A network that keeps every request it gets and answers each with one fixed response.

    It stands in for the transport that opens connections, so no test connects (TEST-16).
    """

    def __init__(
        self, status: HTTPStatus = HTTPStatus.OK, headers: Mapping[str, str] | None = None
    ) -> None:
        """Set the response.

        Args:
            status: The status of every response.
            headers: The headers of every response; none when None.
        """
        self.requests: list[httpx.Request] = []
        self.closed = False
        self._status = status
        self._headers = dict(headers or {})

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Keep the request and answer it.

        Args:
            request: The request.

        Returns:
            The fixed response.
        """
        self.requests.append(request)
        return httpx.Response(self._status, headers=self._headers, request=request)

    def close(self) -> None:
        """Record that the network was closed."""
        self.closed = True


@dataclass(slots=True)
class RecordingEgressClientFactory:
    """Create clients with the real `create_egress_client`, and keep each one.

    A test puts it in place of the factory where the composition root calls it, so the test
    checks the very client that the composition root creates.

    Attributes:
        created: Each created client, with the allow-list it was created from, in order.
    """

    created: list[tuple[EgressAllowList, httpx.Client]] = field(
        default_factory=list[tuple[EgressAllowList, httpx.Client]]
    )

    def __call__(
        self, allow_list: EgressAllowList, network: httpx.BaseTransport | None = None
    ) -> httpx.Client:
        """Create a client with the real factory and keep it.

        Args:
            allow_list: The allow-list.
            network: The network transport; a real one when None.

        Returns:
            The client.
        """
        client = create_egress_client(allow_list, network)
        self.created.append((allow_list, client))
        return client
