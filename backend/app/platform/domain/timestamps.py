"""Timestamps as the contracts write them: RFC 3339 in UTC with `Z` (CON-17, PY-26).

Every layer writes and reads contract timestamps here: the interface layer for `backend`
responses, and the adapters for the bodies that backend sends to and receives from ai-service.
"""

from datetime import datetime, timedelta

from app.platform.domain.errors import UnexpectedFailureError

UTC_OFFSET = timedelta(0)
_UTC_DESIGNATOR = "Z"


class NonUtcTimestampError(UnexpectedFailureError):
    """A timestamp is naive or not in UTC where the contract requires UTC: a defect (PY-26)."""


def format_timestamp(moment: datetime) -> str:
    """Write a time as the contract's `Timestamp`: RFC 3339 in UTC with `Z` (CON-17).

    Args:
        moment: A timezone-aware time in UTC.

    Returns:
        The time with seconds, and microseconds only when they are not zero.

    Raises:
        NonUtcTimestampError: The time is naive or not in UTC.
    """
    if moment.utcoffset() != UTC_OFFSET:
        raise NonUtcTimestampError
    timespec = "microseconds" if moment.microsecond else "seconds"
    return moment.replace(tzinfo=None).isoformat(timespec=timespec) + _UTC_DESIGNATOR


def parse_timestamp(text: str) -> datetime:
    """Read a contract `Timestamp` that a schema already validated.

    Args:
        text: An RFC 3339 time in UTC with `Z`, as the `Timestamp` pattern allows.

    Returns:
        The timezone-aware time.

    Raises:
        NonUtcTimestampError: The text is not a time in UTC.
    """
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        raise NonUtcTimestampError from error
    if moment.utcoffset() != UTC_OFFSET:
        raise NonUtcTimestampError
    return moment
