"""The period of a report and the rules that every figure of it follows (FR-10).

Every figure counts the records whose time falls in the period [`start_at`, `end_at`). The
adapters count in PostgreSQL; these rules decide the order of the items by code, the shares, and
the averages, and which of them are absent because nothing was counted (contracts v1 design,
Reports; contract `ConsoleReport`).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from supportiq_backend.reports.domain.errors import InvalidReportPeriodError


@dataclass(frozen=True, slots=True)
class ReportPeriod:
    """The period of a report: `start_at` included, `end_at` excluded.

    Only `build_report_period` creates one, so `start_at` is always earlier than `end_at`.

    Attributes:
        start_at: The start, included; timezone-aware.
        end_at: The end, excluded: a record at exactly `end_at` belongs to the next period.
    """

    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, slots=True)
class CodeCount[CodeT: StrEnum]:
    """The number of records that carry one code or have one status.

    Attributes:
        code: The code or the status.
        count: The records, at least one.
    """

    code: CodeT
    count: int


def build_report_period(start_at: datetime, end_at: datetime) -> ReportPeriod:
    """Check that a period has a start earlier than its end.

    Args:
        start_at: The start, included.
        end_at: The end, excluded.

    Returns:
        The period.

    Raises:
        InvalidReportPeriodError: `start_at` is not earlier than `end_at`.
    """
    if start_at >= end_at:
        raise InvalidReportPeriodError
    return ReportPeriod(start_at, end_at)


def order_code_counts[CodeT: StrEnum](
    count_by_code: Mapping[CodeT, int], codes_in_order: Iterable[CodeT]
) -> tuple[CodeCount[CodeT], ...]:
    """List one item per code that occurs, in the order of the contract's enum.

    Args:
        count_by_code: The records by code; a code that is missing or counted 0 is left out.
        codes_in_order: Every code, in the order of the contract.

    Returns:
        The items, each with a count of at least one.
    """
    return tuple(
        CodeCount(code, count_by_code[code])
        for code in codes_in_order
        if count_by_code.get(code, 0) > 0
    )


def compute_share(count: int, total: int) -> float | None:
    """Divide a count by the total it belongs to.

    Args:
        count: The part, from 0 to `total`.
        total: The whole.

    Returns:
        A number from 0 to 1, or None when `total` is 0, because nothing was counted.
    """
    if total == 0:
        return None
    return count / total


def compute_rounded_average(total: int, count: int) -> int | None:
    """Divide a total by a count and round to the nearest integer, halves upward.

    Args:
        total: The sum of the values, at least 0.
        count: The number of values, at least 0.

    Returns:
        The rounded average, or None when `count` is 0.
    """
    if count == 0:
        return None
    # Integer arithmetic, so no float rounding: floor((2 * total + count) / (2 * count)).
    return (2 * total + count) // (2 * count)
