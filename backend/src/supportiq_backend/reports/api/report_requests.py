"""The period of `getConsoleReport`: its parameters `ReportStartAt` and `ReportEndAt`.

Each of `start_at` and `end_at` is a required contract `Timestamp`: RFC 3339 in UTC with `Z`
and at most microsecond precision (CON-17). A value that is missing, does not match that
pattern, or names no real time returns `422` with the parameter's name, never its value; a
start that is not earlier than the end returns the detail of the example `invalid-period`.
"""

import re
from datetime import datetime

from supportiq_backend.platform import InvalidParameterError, NonUtcTimestampError, parse_timestamp
from supportiq_backend.reports.domain import ReportPeriod, build_report_period

START_AT_PARAMETER = "start_at"
END_AT_PARAMETER = "end_at"
# The pattern of the contract's `Timestamp` schema.
_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z"
)


def parse_report_period(start_at: str | None, end_at: str | None) -> ReportPeriod:
    """Read the period of a report from its two query parameters.

    Args:
        start_at: The `start_at` parameter as sent, or None when absent.
        end_at: The `end_at` parameter as sent, or None when absent.

    Returns:
        The period.

    Raises:
        InvalidParameterError: A parameter is missing or not a `Timestamp`; `start_at` is
            checked first.
        InvalidReportPeriodError: `start_at` is not earlier than `end_at`.
    """
    return build_report_period(
        parse_report_timestamp(start_at, START_AT_PARAMETER),
        parse_report_timestamp(end_at, END_AT_PARAMETER),
    )


def parse_report_timestamp(raw: str | None, name: str) -> datetime:
    """Read one required `Timestamp` parameter.

    Args:
        raw: The parameter as sent, or None when absent.
        name: The name of the parameter, for the error.

    Returns:
        The timezone-aware time in UTC.

    Raises:
        InvalidParameterError: The value is missing, does not match the pattern, or names no
            real time, such as a 13th month.
    """
    if raw is None or _TIMESTAMP_PATTERN.fullmatch(raw) is None:
        raise InvalidParameterError(name)
    try:
        return parse_timestamp(raw)
    except NonUtcTimestampError as error:
        raise InvalidParameterError(name) from error
