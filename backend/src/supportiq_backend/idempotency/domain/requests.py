"""Idempotent write requests: keys, request hashes, and stored responses (ERR-15).

A key belongs to one account and one operation. A request with a used key and the same
canonical request returns the stored response; with a different one, it is refused. Only a
success is stored: after an error, the record is rolled back with everything else, so the
same key runs as a new request (contract, `Idempotency-Key`).
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import NewType
from uuid import UUID

from supportiq_backend.idempotency.domain.errors import (
    IdempotencyKeyReusedError,
    IdempotencyRecordIncompleteError,
    InvalidIdempotencyKeyError,
)
from supportiq_backend.platform import OperationId

_KEY_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# A key as the contract defines it: a UUID in lowercase hexadecimal with hyphens.
IdempotencyKey = NewType("IdempotencyKey", UUID)
# The account that sent the request, as a canonical UUID text. Internal.
RequesterId = NewType("RequesterId", str)
# The SHA-256 of the canonical request. Internal.
RequestHash = NewType("RequestHash", bytes)
# The values of a canonical request: the body fields and path parameters of a write.
type CanonicalValue = str | int | bool


@dataclass(frozen=True, slots=True)
class IdempotentRequest:
    """One write request with its key.

    Attributes:
        requester_id: The account that sent it; keys of different accounts never meet.
        operation: The operation; keys of different operations never meet.
        key: The `Idempotency-Key`.
        request_hash: The hash of the canonical request.
    """

    requester_id: RequesterId
    operation: OperationId
    key: IdempotencyKey
    request_hash: RequestHash


@dataclass(frozen=True, slots=True)
class StoredResponse:
    """The response of a successful write, returned again, unchanged, to every repeat.

    Attributes:
        status_code: The HTTP status, `201` for the writes of this version.
        body: The exact JSON text of the body. Confidential: a ticket holds a message.
    """

    status_code: int
    body: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class NewRequest:
    """The key was not used: the record is inserted and the write runs."""


@dataclass(frozen=True, slots=True)
class RepeatedRequest:
    """The key was used with the same request: return the stored response.

    Attributes:
        response: The response of the first request.
    """

    response: StoredResponse


@dataclass(frozen=True, slots=True)
class ExistingRecord:
    """The committed record of a key that a request tried to claim.

    Attributes:
        request_hash: The hash of the request that first used the key.
        response: The stored response, or None while that request is still running.
    """

    request_hash: RequestHash
    response: StoredResponse | None


type ClaimOutcome = NewRequest | RepeatedRequest


def parse_idempotency_key(raw: str | None) -> IdempotencyKey:
    """Parse the `Idempotency-Key` header.

    Args:
        raw: The header value, or None when absent.

    Returns:
        The key.

    Raises:
        InvalidIdempotencyKeyError: The header is absent or not a lowercase UUID.
    """
    if raw is None or _KEY_PATTERN.fullmatch(raw) is None:
        raise InvalidIdempotencyKeyError
    return IdempotencyKey(UUID(raw))


def compute_request_hash(request: Mapping[str, CanonicalValue]) -> RequestHash:
    """Hash the canonical form of a request, so key order and whitespace do not matter.

    The canonical form is the JSON of the parsed values with sorted keys and no whitespace
    between tokens. Spaces inside a value, such as a message, are part of the value.

    Args:
        request: The body fields and path parameters of the request.

    Returns:
        The SHA-256 of the canonical form.
    """
    canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return RequestHash(hashlib.sha256(canonical.encode()).digest())


def build_idempotent_request(
    requester_id: RequesterId,
    operation: OperationId,
    key: IdempotencyKey,
    request: Mapping[str, CanonicalValue],
) -> IdempotentRequest:
    """Build an idempotent request from the canonical form of a write.

    Args:
        requester_id: The account that sent the request.
        operation: The operation.
        key: The `Idempotency-Key`.
        request: The body fields and path parameters of the request.

    Returns:
        The request with its hash.
    """
    return IdempotentRequest(requester_id, operation, key, compute_request_hash(request))


def resolve_existing_record(record: ExistingRecord, request: IdempotentRequest) -> RepeatedRequest:
    """Decide what a request with a used key gets.

    Args:
        record: The committed record of the key.
        request: The request that tried to claim it.

    Returns:
        The stored response, for a repeat of the same request.

    Raises:
        IdempotencyKeyReusedError: The key was used with a different request (409).
        IdempotencyRecordIncompleteError: The committed record has no response, which no
            write ever commits: a defect.
    """
    if record.request_hash != request.request_hash:
        raise IdempotencyKeyReusedError
    if record.response is None:
        raise IdempotencyRecordIncompleteError
    return RepeatedRequest(record.response)
