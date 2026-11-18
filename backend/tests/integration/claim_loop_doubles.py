"""Doubles for the tests that run the claim loop of a replica (TEST-14).

The waits of `WakeUpOnlyClock` end when they are cancelled, or at once after a failed claim, so
only a wake-up, a stop, or a failed claim ends a poll wait of the loop, the time never moves,
and no lease expires during a test. `SignallingEventRecorder` lets a test wait for an event
instead of polling, so no test waits for real time.
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

    def failed_claim_count(self) -> int:
        """Return how many claims failed so far.

        The claim loop records a failed claim as `suggestion_job.failed` without a ticket, and a
        failed attempt of a job with its ticket.

        Returns:
            The number of failed claims.
        """
        return sum(
            name is EventName.SUGGESTION_JOB_FAILED and "ticket_id" not in attributes
            for name, attributes in self._recorded
        )

    def _keep(self, event: EventName, attributes: Mapping[str, EventAttributeValue]) -> None:
        self._recorded.append((event, attributes))
        self._changed.set()


class WakeUpOnlyClock(FakeClock):
    """A fake clock whose waits end when cancelled, or at once after a failed claim.

    After a failed claim, the claim loop sleeps its poll interval and claims again. A wait of
    this clock never ends by itself, so without the failed claim rule, one transient failure of
    PostgreSQL would leave the job queued until the bound of the test.
    """

    def __init__(self, events: SignallingEventRecorder) -> None:
        """Start the clock at the fake start time, with no wait yet.

        Args:
            events: The recorder of the replica, which counts its failed claims.
        """
        super().__init__()
        self.is_waiting = asyncio.Event()
        self._events = events
        self._failed_claims_seen = 0

    async def sleep(self, duration_ms: int) -> None:
        """Record the wait; end it at once after a new failed claim, or when it is cancelled.

        The time does not move either way, so no lease expires.

        Args:
            duration_ms: The duration of the wait, in milliseconds.
        """
        self.sleeps_ms.append(duration_ms)
        failed_claims = self._events.failed_claim_count()
        if failed_claims > self._failed_claims_seen:
            self._failed_claims_seen = failed_claims
            return
        self.is_waiting.set()
        await asyncio.Event().wait()
