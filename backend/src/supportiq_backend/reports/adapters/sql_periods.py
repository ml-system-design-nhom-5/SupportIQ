"""SQL expressions over a report period: the period filter and durations in whole milliseconds.

Every figure and every export record uses these, so a record at exactly `start_at` is always
counted and one at exactly `end_at` never is, and every duration is rounded the same way.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, Numeric, and_, cast, extract, func

from supportiq_backend.platform import MILLISECONDS_PER_SECOND
from supportiq_backend.reports.domain import ReportPeriod

_MEDIAN = 0.5
_P95 = 0.95
_NUMERIC = Numeric()


def in_period(moment: ColumnElement[datetime], period: ReportPeriod) -> ColumnElement[bool]:
    """Tell whether a time falls in [`start_at`, `end_at`); NULL never does.

    Args:
        moment: A `timestamptz` column.
        period: The period.

    Returns:
        The condition.
    """
    return and_(moment >= period.start_at, moment < period.end_at)


def to_whole_milliseconds(duration: ColumnElement[timedelta]) -> ColumnElement[Decimal]:
    """Turn an interval into whole milliseconds, rounding halves away from zero.

    `extract` returns `numeric`, whose `round` breaks ties away from zero on every platform
    (PostgreSQL 17, Mathematical Functions), so the result never depends on float rounding.

    Args:
        duration: An `interval` expression; NULL stays NULL.

    Returns:
        The milliseconds, as a `numeric` without a fraction.
    """
    milliseconds = cast(extract("epoch", duration), _NUMERIC) * MILLISECONDS_PER_SECOND
    return func.round(milliseconds, type_=_NUMERIC)


def median_ms(duration: ColumnElement[timedelta]) -> ColumnElement[Decimal]:
    """Return the median of an interval over the group, in whole milliseconds.

    Args:
        duration: An `interval` expression.

    Returns:
        The `percentile_cont` median; NULL for an empty group.
    """
    return to_whole_milliseconds(func.percentile_cont(_MEDIAN).within_group(duration))


def p95_ms(duration: ColumnElement[timedelta]) -> ColumnElement[Decimal]:
    """Return the 95th percentile of an interval over the group, in whole milliseconds.

    Args:
        duration: An `interval` expression.

    Returns:
        The `percentile_cont` 95th percentile; NULL for an empty group.
    """
    return to_whole_milliseconds(func.percentile_cont(_P95).within_group(duration))


def to_optional_milliseconds(value: Decimal | None) -> int | None:
    """Read a rounded duration of `to_whole_milliseconds` as an integer.

    Args:
        value: The `numeric` value, or None for NULL.

    Returns:
        The milliseconds, or None.
    """
    return None if value is None else int(value)
