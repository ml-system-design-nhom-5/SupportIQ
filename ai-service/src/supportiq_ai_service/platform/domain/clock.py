"""The clock port, so tests control time instead of waiting (TEST-14)."""

from datetime import datetime
from typing import Protocol

MILLISECONDS_PER_SECOND = 1_000


class Clock(Protocol):
    """Tell the current time."""

    def now(self) -> datetime:
        """Return the current time.

        Returns:
            A timezone-aware time in UTC.
        """
        ...
