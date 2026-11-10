"""Tests of the `limit` and `cursor` parameters (CON-14, CON-15)."""

import base64
from datetime import UTC, datetime

import pytest

from supportiq_backend.platform import InvalidCursorError, InvalidLimitError
from supportiq_backend.platform.web import (
    CURSOR_MAX_LENGTH,
    CursorTooLongError,
    decode_cursor,
    encode_cursor,
    parse_limit,
)

OPERATION = "listShopProducts"
FIELDS = frozenset({"name", "product_id"})


def encode_text(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


@pytest.mark.parametrize(
    ("raw", "page_size"),
    [(None, 20), ("1", 1), ("2", 2), ("99", 99), ("100", 100), ("020", 20)],
)
def test_parse_limit_accepts_integers_from_1_to_100(raw: str | None, page_size: int) -> None:
    parsed = parse_limit(raw)

    assert parsed == page_size


@pytest.mark.parametrize("raw", ["0", "101", "1000", "-1", "+5", "1.5", "1e2", "abc", "", " 5"])
def test_parse_limit_refuses_every_other_value(raw: str) -> None:
    with pytest.raises(InvalidLimitError):
        parse_limit(raw)


def test_cursor_round_trip_returns_the_same_fields() -> None:
    cursor = encode_cursor(OPERATION, {"name": "Đèn bàn", "product_id": "PRD-1001"})

    fields = decode_cursor(cursor, OPERATION, FIELDS)

    assert fields is not None
    assert (fields.text("name"), fields.text("product_id")) == ("Đèn bàn", "PRD-1001")


def test_cursor_is_url_safe_without_padding() -> None:
    cursor = encode_cursor("listShopOrders", {"position": 20})

    assert set(cursor) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_absent_cursor_means_the_first_page() -> None:
    fields = decode_cursor(None, OPERATION, FIELDS)

    assert fields is None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "!!!",
        "a",
        "x" * (CURSOR_MAX_LENGTH + 1),
        encode_text("not json"),
        encode_text("[1, 2]"),
        encode_text('{"op": "listShopOrders", "name": "a", "product_id": "b"}'),
        encode_text('{"name": "a", "product_id": "b"}'),
        encode_text('{"op": "listShopProducts", "name": "a"}'),
        encode_text('{"op": "listShopProducts", "name": "a", "product_id": "b", "x": 1}'),
        base64.urlsafe_b64encode(b"\xff\xfe").rstrip(b"=").decode(),
    ],
)
def test_decode_cursor_refuses_a_malformed_or_foreign_cursor(raw: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(raw, OPERATION, FIELDS)


@pytest.mark.parametrize("value", ['""', "7", "null", "true"])
def test_cursor_text_field_refuses_an_empty_or_non_text_value(value: str) -> None:
    raw = encode_text(f'{{"op": "listShopProducts", "name": {value}, "product_id": "b"}}')
    fields = decode_cursor(raw, OPERATION, FIELDS)
    assert fields is not None

    with pytest.raises(InvalidCursorError):
        fields.text("name")


@pytest.mark.parametrize("value", ["-1", "true", '"3"', "1.5"])
def test_cursor_number_field_refuses_a_negative_or_non_integer_value(value: str) -> None:
    raw = encode_text(f'{{"op": "listShopOrders", "position": {value}}}')
    fields = decode_cursor(raw, "listShopOrders", frozenset({"position"}))
    assert fields is not None

    with pytest.raises(InvalidCursorError):
        fields.natural_number("position")


def test_cursor_number_field_accepts_zero() -> None:
    raw = encode_cursor("listShopOrders", {"position": 0})
    fields = decode_cursor(raw, "listShopOrders", frozenset({"position"}))
    assert fields is not None

    position = fields.natural_number("position")

    assert position == 0


def test_cursor_number_field_accepts_the_largest_bigint() -> None:
    raw = encode_cursor("listShopOrders", {"position": 2**63 - 1})
    fields = decode_cursor(raw, "listShopOrders", frozenset({"position"}))
    assert fields is not None

    position = fields.natural_number("position")

    assert position == 2**63 - 1


def test_cursor_number_field_refuses_a_value_beyond_a_bigint() -> None:
    raw = encode_cursor("listShopOrders", {"position": 2**63})
    fields = decode_cursor(raw, "listShopOrders", frozenset({"position"}))
    assert fields is not None

    with pytest.raises(InvalidCursorError):
        fields.natural_number("position")


def test_cursor_text_field_refuses_a_nul_character() -> None:
    raw = encode_cursor(OPERATION, {"name": "a\x00b", "product_id": "PRD-1"})
    fields = decode_cursor(raw, OPERATION, FIELDS)
    assert fields is not None

    with pytest.raises(InvalidCursorError):
        fields.text("name")


@pytest.mark.parametrize(
    ("value", "moment"),
    [
        ("2026-11-05T09:00:00Z", datetime(2026, 11, 5, 9, tzinfo=UTC)),
        ("2026-11-05T09:00:00.000001Z", datetime(2026, 11, 5, 9, 0, 0, 1, tzinfo=UTC)),
    ],
)
def test_cursor_timestamp_field_keeps_the_exact_time(value: str, moment: datetime) -> None:
    raw = encode_cursor("listShopTickets", {"created_at": value})
    fields = decode_cursor(raw, "listShopTickets", frozenset({"created_at"}))
    assert fields is not None

    parsed = fields.timestamp("created_at")

    assert parsed == moment


@pytest.mark.parametrize(
    "value",
    ["not a time", "2026-11-05T09:00:00", "2026-11-05T16:00:00+07:00", "2026-13-05T09:00:00Z"],
)
def test_cursor_timestamp_field_refuses_anything_but_a_time_in_utc(value: str) -> None:
    raw = encode_cursor("listShopTickets", {"created_at": value})
    fields = decode_cursor(raw, "listShopTickets", frozenset({"created_at"}))
    assert fields is not None

    with pytest.raises(InvalidCursorError):
        fields.timestamp("created_at")


def test_encode_cursor_refuses_a_cursor_longer_than_the_contract_allows() -> None:
    with pytest.raises(CursorTooLongError):
        encode_cursor(OPERATION, {"name": "x" * CURSOR_MAX_LENGTH, "product_id": "PRD-1"})
