"""Tests of strict body parsing, validation locations, and response writing (SEC-21, CON-17)."""

import json
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from starlette.requests import Request
from starlette.types import Message

from supportiq_backend.generated import ChangeAccountStatusRequest, ShipmentStatus, ShopShipmentView
from supportiq_backend.platform import RequestContractError
from supportiq_backend.platform.web import (
    NonUtcTimestampError,
    format_timestamp,
    locations_of,
    parse_json_body,
    render_json,
)

pytestmark = pytest.mark.anyio

# The pattern of contracts/schemas/Timestamp.yaml.
CONTRACT_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z$"
)


def build_request(body: bytes) -> Request:
    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "headers": [], "path": "/"}, receive)


async def test_parse_json_body_returns_the_contract_model() -> None:
    request = build_request(b'{"is_active": false}')

    parsed = await parse_json_body(request, ChangeAccountStatusRequest)

    assert parsed.is_active is False


@pytest.mark.parametrize(
    ("body", "location"),
    [
        (b'{"is_active": "false"}', "body.is_active"),
        (b'{"is_active": 0}', "body.is_active"),
        (b"{}", "body.is_active"),
        (b'{"is_active": true, "role": "admin"}', "body.role"),
        (b"{not json", "body"),
        (b"", "body"),
    ],
)
async def test_parse_json_body_refuses_a_body_outside_the_contract(
    body: bytes, location: str
) -> None:
    request = build_request(body)

    with pytest.raises(RequestContractError) as caught:
        await parse_json_body(request, ChangeAccountStatusRequest)

    assert caught.value.locations == (location,)


async def test_contract_error_detail_never_repeats_the_value_that_was_sent() -> None:
    request = build_request(b'{"is_active": "Lan Tran"}')

    with pytest.raises(RequestContractError) as caught:
        await parse_json_body(request, ChangeAccountStatusRequest)

    assert "Lan Tran" not in caught.value.detail


def test_locations_of_joins_names_and_removes_repeats() -> None:
    errors = [{"loc": ("header", "idempotency-key")}, {"loc": ("header", "idempotency-key")}]

    locations = locations_of(errors)

    assert locations == ("header.idempotency-key",)


def test_locations_of_names_the_whole_request_for_an_error_without_location() -> None:
    locations = locations_of([{"loc": ()}])

    assert locations == ("request",)


@pytest.mark.parametrize(
    ("moment", "text"),
    [
        (datetime(2026, 11, 5, 9, 30, tzinfo=UTC), "2026-11-05T09:30:00Z"),
        (datetime(2026, 11, 5, 9, 30, 0, 125_000, tzinfo=UTC), "2026-11-05T09:30:00.125000Z"),
        (datetime(2026, 11, 5, 9, 30, 0, 1, tzinfo=UTC), "2026-11-05T09:30:00.000001Z"),
        (datetime(2026, 11, 5, 9, 30, tzinfo=timezone(timedelta(0))), "2026-11-05T09:30:00Z"),
    ],
)
def test_format_timestamp_writes_the_contract_timestamp(moment: datetime, text: str) -> None:
    formatted = format_timestamp(moment)

    assert formatted == text
    assert CONTRACT_TIMESTAMP_PATTERN.fullmatch(formatted)


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 11, 5, 9, 30, tzinfo=UTC).replace(tzinfo=None),
        datetime(2026, 11, 5, 16, 30, tzinfo=timezone(timedelta(hours=7))),
    ],
)
def test_format_timestamp_refuses_a_time_that_is_not_utc(moment: datetime) -> None:
    with pytest.raises(NonUtcTimestampError):
        format_timestamp(moment)


def test_render_json_leaves_absent_optional_fields_absent() -> None:
    shipment = ShopShipmentView(shipment_status=ShipmentStatus.not_shipped)

    body = json.loads(render_json(shipment))

    assert body == {"shipment_status": "not_shipped"}
