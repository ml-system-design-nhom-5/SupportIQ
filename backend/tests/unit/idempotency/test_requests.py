"""Tests of idempotency keys, canonical request hashes, and existing records (ERR-15)."""

from uuid import UUID

import pytest

from supportiq_backend.idempotency import (
    ExistingRecord,
    IdempotencyKey,
    IdempotencyKeyReusedError,
    IdempotencyRecordIncompleteError,
    InvalidIdempotencyKeyError,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
    compute_request_hash,
    parse_idempotency_key,
    resolve_existing_record,
)
from supportiq_backend.platform import OperationId

KEY_TEXT = "00000000-0000-4000-8000-000000000001"
REQUESTER = RequesterId("5f0c2a8e-3b1d-4c7a-9e2f-1a6b8d4c0e31")
# SHA-256 of {"message":"Hi","order_id":"ORD-00001"}, the canonical form of this request.
EXPECTED_HASH = bytes.fromhex("db03851fc03c8393c143c1c0ebe2adea5392cf05bcf84736df1fe05bb3be89f7")
BODY = '{"ticket_id":"TCK-1001"}'
RESPONSE = StoredResponse(201, BODY)
REQUEST = build_idempotent_request(
    REQUESTER, OperationId.CREATE_SHOP_TICKET, IdempotencyKey(UUID(KEY_TEXT)), {}
)


def test_parse_idempotency_key_accepts_a_lowercase_uuid() -> None:
    key = parse_idempotency_key(KEY_TEXT)

    assert key == UUID(KEY_TEXT)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "0000000A-0000-4000-8000-00000000000A",
        "{" + KEY_TEXT + "}",
        KEY_TEXT.replace("-", ""),
        " " + KEY_TEXT,
        KEY_TEXT + "0",
        "not-a-key",
    ],
)
def test_parse_idempotency_key_refuses_anything_else(raw: str | None) -> None:
    with pytest.raises(InvalidIdempotencyKeyError):
        parse_idempotency_key(raw)


def test_request_hash_is_the_sha256_of_the_canonical_json() -> None:
    request_hash = compute_request_hash({"order_id": "ORD-00001", "message": "Hi"})

    assert request_hash == EXPECTED_HASH


def test_request_hash_ignores_the_order_of_the_fields() -> None:
    first = compute_request_hash({"order_id": "ORD-00001", "message": "Hi"})
    second = compute_request_hash({"message": "Hi", "order_id": "ORD-00001"})

    assert first == second


@pytest.mark.parametrize("other_message", ["Hi ", " Hi", "hi", "Hi\n", "Hì"])
def test_request_hash_keeps_every_character_of_a_value(other_message: str) -> None:
    first = compute_request_hash({"message": "Hi"})
    second = compute_request_hash({"message": other_message})

    assert first != second


def test_request_hash_tells_a_boolean_from_a_text() -> None:
    first = compute_request_hash({"is_active": True})
    second = compute_request_hash({"is_active": "true"})

    assert first != second


def test_existing_record_of_the_same_request_returns_its_response() -> None:
    outcome = resolve_existing_record(ExistingRecord(REQUEST.request_hash, RESPONSE), REQUEST)

    assert outcome == RepeatedRequest(RESPONSE)


def test_existing_record_of_another_request_is_refused() -> None:
    other_hash = compute_request_hash({"message": "Hi"})

    with pytest.raises(IdempotencyKeyReusedError):
        resolve_existing_record(ExistingRecord(other_hash, RESPONSE), REQUEST)


def test_existing_record_without_a_response_is_a_defect() -> None:
    with pytest.raises(IdempotencyRecordIncompleteError):
        resolve_existing_record(ExistingRecord(REQUEST.request_hash, None), REQUEST)


def test_stored_response_hides_its_body_in_its_repr() -> None:
    text = repr(RESPONSE)

    assert BODY not in text
