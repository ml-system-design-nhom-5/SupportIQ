"""The system clock, the production implementation of the `Clock` port."""

from datetime import UTC, datetime


class SystemClock:
    """Implement the `Clock` port with the system time."""

    def now(self) -> datetime:
        """Return the current time in UTC."""
        return datetime.now(UTC)
