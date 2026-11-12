"""Doubles for the tests that run the claim loop of a replica (TEST-14).

The waits of `WakeUpOnlyClock` end only when they are cancelled, so only a wake-up or a stop
ends a poll wait of the loop, the time never moves, and no lease expires during a test.
`SignallingEventRecorder` lets a test wait for an event instead of polling, so no test waits
for real time.
"""

import asyncio
from collections.abc import Mapping

from supportiq_backend.platform import EventAttributeValue, EventName, EventRecorder
from tests.unit.platform.fakes import FakeClock


class SignallingEventRecorder:
    """Pass every event to another recorder, and let a test wait until one was recorded."""

    def __init__(self, inner: EventRecorder) -> None:
        """Start with no event.

        Args:
            inner: The recorder that keeps or logs every event.
        """
        self._inner = inner
        self._recorded: list[tuple[EventName, Mapping[str, EventAttributeValue]]] = []
        self._changed = asyncio.Event()

    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Pass the event on and wake the tests that wait.

        Args:
            event: The event.
            **attributes: Its attributes.
        """
        self._inner.record(event, **attributes)
        self._keep(event, attributes)

    def record_handled_input(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Pass the event caused by handled input on and wake the tests that wait.

        Args:
            event: The event.
            **attributes: Its attributes.
        """
        self._inner.record_handled_input(event, **attributes)
        self._keep(event, attributes)

    async def wait_for(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Return once the event was recorded with at least these attributes.

        Args:
            event: The event.
            **attributes: Attributes that the event must carry, with these values.
        """
        while not any(
            name is event and attributes.items() <= recorded.items()
            for name, recorded in self._recorded
        ):
            self._changed.clear()
            await self._changed.wait()

    def _keep(self, event: EventName, attributes: Mapping[str, EventAttributeValue]) -> None:
        self._recorded.append((event, attributes))
        self._changed.set()


class WakeUpOnlyClock(FakeClock):
    """A fake clock whose waits end only when cancelled, so only a wake-up ends a poll wait."""

    def __init__(self) -> None:
        """Start the clock at the fake start time, with no wait yet."""
        super().__init__()
        self.is_waiting = asyncio.Event()

    async def sleep(self, duration_ms: int) -> None:
        """Record the wait, and wait until it is cancelled; the time does not move.

        Args:
            duration_ms: The duration of the wait, in milliseconds.
        """
        self.sleeps_ms.append(duration_ms)
        self.is_waiting.set()
        await asyncio.Event().wait()
