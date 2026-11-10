"""Domain of idempotency: keys, request hashes, stored responses, and the store port."""

from supportiq_backend.idempotency.domain.errors import (
    IdempotencyKeyReusedError,
    IdempotencyRecordIncompleteError,
    InvalidIdempotencyKeyError,
)
from supportiq_backend.idempotency.domain.ports import IdempotencyStore
from supportiq_backend.idempotency.domain.requests import (
    CanonicalValue,
    ClaimOutcome,
    ExistingRecord,
    IdempotencyKey,
    IdempotentRequest,
    NewRequest,
    RepeatedRequest,
    RequesterId,
    RequestHash,
    StoredResponse,
    build_idempotent_request,
    compute_request_hash,
    parse_idempotency_key,
    resolve_existing_record,
)

__all__ = [
    "CanonicalValue",
    "ClaimOutcome",
    "ExistingRecord",
    "IdempotencyKey",
    "IdempotencyKeyReusedError",
    "IdempotencyRecordIncompleteError",
    "IdempotencyStore",
    "IdempotentRequest",
    "InvalidIdempotencyKeyError",
    "NewRequest",
    "RepeatedRequest",
    "RequestHash",
    "RequesterId",
    "StoredResponse",
    "build_idempotent_request",
    "compute_request_hash",
    "parse_idempotency_key",
    "resolve_existing_record",
]
