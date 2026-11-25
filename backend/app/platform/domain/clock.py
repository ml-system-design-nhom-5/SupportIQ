"""The clock port: the only source of the current time and of waits (ARCH-31, PY-26)."""

from datetime import datetime
from typing import Protocol

MILLISECONDS_PER_SECOND = 1_000


class Clock(Protocol):
    """Tell the current time and wait for a duration.

    Domain and application code never read the system time or sleep directly (CODE-18), so
    tests replace the clock with a fake that never waits (TEST-14).
    """

    def now(self) -> datetime:
        """Return the current time.

        Returns:
            A timezone-aware datetime in UTC.
        """
        ...

    async def sleep(self, duration_ms: int) -> None:
        """Wait for a duration without blocking the event loop.

        Args:
            duration_ms: How long to wait, in milliseconds.
        """
        ...
