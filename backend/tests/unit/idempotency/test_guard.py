"""Tests of the guard that every retryable write runs first (ERR-15)."""

from datetime import timedelta
from uuid import UUID

import pytest

from supportiq_backend.idempotency import (
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyKeyReusedError,
    NewRequest,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import OperationId
from tests.unit.idempotency.fakes import FakeIdempotencyStore
from tests.unit.platform.fakes import FakeClock

pytestmark = pytest.mark.anyio

RETENTION_MS = 86_400_000
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000001"))
REQUESTER = RequesterId("5f0c2a8e-3b1d-4c7a-9e2f-1a6b8d4c0e31")
REQUEST = build_idempotent_request(
    REQUESTER, OperationId.CREATE_SHOP_TICKET, KEY, {"message": "Hi"}
)
OTHER_REQUEST = build_idempotent_request(
    REQUESTER, OperationId.CREATE_SHOP_TICKET, KEY, {"message": "Hello"}
)
RESPONSE = StoredResponse(201, '{"ticket_id":"TCK-1001"}')


async def test_claim_of_an_unused_key_runs_the_write() -> None:
    store = FakeIdempotencyStore()
    guard = IdempotencyGuard(FakeClock(), RETENTION_MS)

    outcome = await guard.claim(store, REQUEST)

    assert outcome == NewRequest()


async def test_claim_dates_the_record_and_expires_records_older_than_the_retention() -> None:
    clock = FakeClock()
    store = FakeIdempotencyStore()

    await IdempotencyGuard(clock, RETENTION_MS).claim(store, REQUEST)

    (record,) = store.records.values()
    assert record.created_at == clock.now()
    assert store.expired_before_of_claims == [clock.now() - timedelta(milliseconds=RETENTION_MS)]


async def test_claim_of_a_used_key_with_the_same_request_returns_the_first_response() -> None:
    store = FakeIdempotencyStore()
    guard = IdempotencyGuard(FakeClock(), RETENTION_MS)
    await guard.claim(store, REQUEST)
    await store.save_response(REQUEST, RESPONSE)

    outcome = await guard.claim(store, REQUEST)

    assert outcome == RepeatedRequest(RESPONSE)


async def test_claim_of_a_used_key_with_another_request_is_refused() -> None:
    store = FakeIdempotencyStore()
    guard = IdempotencyGuard(FakeClock(), RETENTION_MS)
    await guard.claim(store, REQUEST)
    await store.save_response(REQUEST, RESPONSE)

    with pytest.raises(IdempotencyKeyReusedError):
        await guard.claim(store, OTHER_REQUEST)


async def test_claim_exactly_at_the_retention_still_returns_the_first_response() -> None:
    clock = FakeClock()
    store = FakeIdempotencyStore()
    guard = IdempotencyGuard(clock, RETENTION_MS)
    await guard.claim(store, REQUEST)
    await store.save_response(REQUEST, RESPONSE)

    clock.advance(RETENTION_MS)
    outcome = await guard.claim(store, REQUEST)

    assert outcome == RepeatedRequest(RESPONSE)


async def test_claim_just_after_the_retention_runs_as_a_new_request() -> None:
    clock = FakeClock()
    store = FakeIdempotencyStore()
    guard = IdempotencyGuard(clock, RETENTION_MS)
    await guard.claim(store, REQUEST)
    await store.save_response(REQUEST, RESPONSE)

    clock.advance(RETENTION_MS + 1)
    outcome = await guard.claim(store, REQUEST)

    assert outcome == NewRequest()
