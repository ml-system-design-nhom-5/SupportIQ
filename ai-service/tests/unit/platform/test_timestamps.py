"""Timestamps are read and written only as the contract's `Timestamp`: UTC with `Z` (CON-17)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.platform import RequestContractError
from app.platform.web import (
    NonUtcTimestampError,
    format_timestamp,
    parse_timestamp,
)

LOCATION = "body.as_of"


@pytest.mark.parametrize(
    ("text", "moment"),
    [
        ("2026-11-05T09:30:00Z", datetime(2026, 11, 5, 9, 30, tzinfo=UTC)),
        ("2026-11-05T09:30:00.125Z", datetime(2026, 11, 5, 9, 30, 0, 125_000, tzinfo=UTC)),
        ("2026-11-05T09:30:00.000001Z", datetime(2026, 11, 5, 9, 30, 0, 1, tzinfo=UTC)),
    ],
)
def test_a_contract_timestamp_is_read_in_utc(text: str, moment: datetime) -> None:
    parsed = parse_timestamp(text, LOCATION)

    assert parsed == moment
    assert parsed.tzinfo is UTC


@pytest.mark.parametrize(
    "text",
    [
        "2026-11-05T09:30:00",
        "2026-11-05T16:30:00+07:00",
        "2026-11-05T09:30:00+00:00",
        "2026-11-05 09:30:00Z",
        "2026-11-05T09:30:00.1234567Z",
        "2026-13-05T09:30:00Z",
        "2026-02-30T09:30:00Z",
        "not a time",
    ],
)
def test_a_time_that_is_not_a_contract_timestamp_is_rejected_at_its_location(text: str) -> None:
    with pytest.raises(RequestContractError) as raised:
        parse_timestamp(text, LOCATION)

    assert raised.value.locations == (LOCATION,)
    assert text not in raised.value.detail


@pytest.mark.parametrize(
    ("moment", "text"),
    [
        (datetime(2026, 11, 5, 9, 30, tzinfo=UTC), "2026-11-05T09:30:00Z"),
        (datetime(2026, 11, 5, 9, 30, 0, 125_000, tzinfo=UTC), "2026-11-05T09:30:00.125000Z"),
    ],
)
def test_a_time_in_utc_is_written_as_a_contract_timestamp(moment: datetime, text: str) -> None:
    assert format_timestamp(moment) == text


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 11, 5, 9, 30, tzinfo=UTC).replace(tzinfo=None),
        datetime(2026, 11, 5, 16, 30, tzinfo=timezone(timedelta(hours=7))),
    ],
)
def test_a_time_that_is_not_in_utc_is_never_written(moment: datetime) -> None:
    with pytest.raises(NonUtcTimestampError):
        format_timestamp(moment)
