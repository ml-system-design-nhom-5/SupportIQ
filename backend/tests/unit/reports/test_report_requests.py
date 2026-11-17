"""The query parameters of `getConsoleReport`: two required `Timestamp` values (CON-17)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from supportiq_backend.platform import InvalidParameterError, TraceId
from supportiq_backend.platform.web import build_problem_response
from supportiq_backend.reports import InvalidReportPeriodError, ReportPeriod
from supportiq_backend.reports.api.report_requests import parse_report_period

PROBLEM_EXAMPLES = Path(__file__).parents[4] / "contracts/examples/problems"
START_TEXT = "2026-11-02T00:00:00Z"
END_TEXT = "2026-11-09T00:00:00Z"
START_AT = datetime(2026, 11, 2, tzinfo=UTC)
END_AT = datetime(2026, 11, 9, tzinfo=UTC)
START_AT_DETAIL = "The parameter start_at is not valid."
END_AT_DETAIL = "The parameter end_at is not valid."
# Values that are not a contract `Timestamp`: no time, an offset instead of `Z`, a lowercase
# `z`, seven fraction digits, no real month, a space instead of `T`, and the empty text.
NOT_TIMESTAMPS = [
    "2026-11-02",
    "2026-11-02T00:00:00+07:00",
    "2026-11-02T00:00:00z",
    "2026-11-02T00:00:00.1234567Z",
    "2026-13-02T00:00:00Z",
    "2026-11-02 00:00:00Z",
    "",
]


def test_period_of_two_timestamps_is_read_in_utc() -> None:
    period = parse_report_period(START_TEXT, END_TEXT)

    assert period == ReportPeriod(START_AT, END_AT)


def test_period_keeps_microseconds() -> None:
    period = parse_report_period("2026-11-02T00:00:00.000001Z", END_TEXT)

    assert period.start_at == START_AT.replace(microsecond=1)


@pytest.mark.parametrize("start_at", [None, *NOT_TIMESTAMPS])
def test_start_that_is_missing_or_not_a_timestamp_is_refused_by_name(start_at: str | None) -> None:
    with pytest.raises(InvalidParameterError) as caught:
        parse_report_period(start_at, END_TEXT)

    assert caught.value.detail == START_AT_DETAIL


@pytest.mark.parametrize("end_at", [None, *NOT_TIMESTAMPS])
def test_end_that_is_missing_or_not_a_timestamp_is_refused_by_name(end_at: str | None) -> None:
    with pytest.raises(InvalidParameterError) as caught:
        parse_report_period(START_TEXT, end_at)

    assert caught.value.detail == END_AT_DETAIL


def test_two_invalid_parameters_name_the_start_first() -> None:
    with pytest.raises(InvalidParameterError) as caught:
        parse_report_period(None, None)

    assert caught.value.detail == START_AT_DETAIL


def test_period_without_duration_is_the_problem_of_the_contract_example() -> None:
    example = json.loads((PROBLEM_EXAMPLES / "invalid-period.json").read_text(encoding="utf-8"))

    with pytest.raises(InvalidReportPeriodError) as caught:
        parse_report_period(START_TEXT, START_TEXT)

    response = build_problem_response(caught.value, TraceId(example["value"]["trace_id"]))
    assert json.loads(bytes(response.body)) == example["value"]
