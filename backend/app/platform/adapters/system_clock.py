"""The real clock: the system time in UTC and asyncio waits (ARCH-31)."""

import asyncio
from datetime import UTC, datetime

from app.platform.domain import MILLISECONDS_PER_SECOND


class SystemClock:
    """Implement the `Clock` port with the system time."""

    def now(self) -> datetime:
        """Return the current time, timezone-aware and in UTC (PY-26)."""
        return datetime.now(UTC)

    async def sleep(self, duration_ms: int) -> None:
        """Wait without blocking the event loop.

        Args:
            duration_ms: How long to wait, in milliseconds.
        """
        await asyncio.sleep(duration_ms / MILLISECONDS_PER_SECOND)
