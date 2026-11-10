"""The request log: one `request.completed` event per HTTP request (LOG-09, LOG-29).

The event carries the method, the route template, the status, and the duration. It never
carries the raw path, the query, or a header, because a URL can hold an order ID and the
`Cookie` header holds the raw session identifier (backend foundation design, Errors and
guardrails).
"""

from dataclasses import dataclass

from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from supportiq_backend.platform import (
    MILLISECONDS_PER_SECOND,
    Clock,
    EventAttributeValue,
    EventName,
    EventRecorder,
)

_NO_STATUS = 0


@dataclass(slots=True)
class _ResponseStatus:
    code: int = _NO_STATUS


class RequestLoggingMiddleware:
    """Record one `request.completed` event for every HTTP request."""

    def __init__(self, app: ASGIApp, events: EventRecorder, clock: Clock) -> None:
        """Wrap the application.

        Args:
            app: The inner application.
            events: Where the event is recorded.
            clock: The clock that measures the duration.
        """
        self._app = app
        self._events = events
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the request and record its outcome.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started_at = self._clock.now()
        status = _ResponseStatus()

        async def send_and_track(message: Message) -> None:
            if message["type"] == "http.response.start":
                status.code = int(message["status"])
            await send(message)

        await self._app(scope, receive, send_and_track)
        elapsed = self._clock.now() - started_at
        attributes: dict[str, EventAttributeValue] = {
            "http_method": str(scope["method"]),
            "http_status_code": status.code,
            "duration_ms": int(elapsed.total_seconds() * MILLISECONDS_PER_SECOND),
        }
        route = scope.get("route")
        if isinstance(route, Route):
            attributes["http_route"] = route.path
        self._events.record(EventName.REQUEST_COMPLETED, **attributes)
