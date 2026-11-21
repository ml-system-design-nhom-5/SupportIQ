"""The clock port, so tests control time instead of waiting (TEST-14), and the contract's time."""

import re
from datetime import datetime
from typing import Protocol

MILLISECONDS_PER_SECOND = 1_000
# The pattern of the contract's `Timestamp`: RFC 3339 in UTC with `Z` and at most microsecond
# precision (CON-17). Requests and the files of a release hold every timestamp in this form.
TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z$"
)


class Clock(Protocol):
    """Tell the current time."""

    def now(self) -> datetime:
        """Return the current time.

        Returns:
            A timezone-aware time in UTC.
        """
        ...
