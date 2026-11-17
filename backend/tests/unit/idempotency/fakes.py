"""In-memory fake of the `IdempotencyStore` port (ARCH-27)."""

import json
from dataclasses import dataclass, field
from datetime import datetime

from supportiq_backend.idempotency import (
    ExistingRecord,
    IdempotencyKey,
    IdempotentRequest,
    NewRequest,
    RequesterId,
    RequestHash,
    StoredResponse,
)
from supportiq_backend.platform import OperationId

type RecordKey = tuple[RequesterId, OperationId, IdempotencyKey]


@dataclass(slots=True)
class FakeRecord:
    """One record of the fake store.

    Attributes:
        request_hash: The hash of the first request.
        created_at: When the record was created.
        response: The stored response, or None while the first request runs.
    """

    request_hash: RequestHash
    created_at: datetime
    response: StoredResponse | None = None


@dataclass(slots=True)
class FakeIdempotencyStore:
    """Keep records in a dictionary; expired records disappear on the next claim."""

    records: dict[RecordKey, FakeRecord] = field(default_factory=dict[RecordKey, FakeRecord])
    expired_before_of_claims: list[datetime] = field(default_factory=list[datetime])

    async def claim(
        self, request: IdempotentRequest, *, now: datetime, expired_before: datetime
    ) -> NewRequest | ExistingRecord:
        """Insert the record of the key, or return the existing one."""
        self.expired_before_of_claims.append(expired_before)
        self.records = {
            key: record
            for key, record in self.records.items()
            if record.created_at >= expired_before
        }
        key = _key_of(request)
        existing = self.records.get(key)
        if existing is not None:
            return ExistingRecord(existing.request_hash, existing.response)
        self.records[key] = FakeRecord(request.request_hash, now)
        return NewRequest()

    async def save_response(self, request: IdempotentRequest, response: StoredResponse) -> None:
        """Store the response in the record of the key; its body must be JSON, as in the table."""
        json.loads(response.body)
        self.records[_key_of(request)].response = response


def _key_of(request: IdempotentRequest) -> RecordKey:
    return (request.requester_id, request.operation, request.key)
