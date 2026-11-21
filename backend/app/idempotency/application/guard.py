"""The guard that every retryable write runs first, inside its own transaction (ERR-15)."""

from datetime import timedelta
from typing import assert_never

from app.idempotency.domain import (
    ClaimOutcome,
    ExistingRecord,
    IdempotencyStore,
    IdempotentRequest,
    NewRequest,
    resolve_existing_record,
)
from app.platform import Clock


class IdempotencyGuard:
    """Claim the key of a write, or return the response of its first request."""

    def __init__(self, clock: Clock, retention_ms: int) -> None:
        """Keep the clock and the retention of the records.

        Args:
            clock: The clock that dates new records.
            retention_ms: How long a record is kept: `idempotency_retention_ms`.
        """
        self._clock = clock
        self._retention = timedelta(milliseconds=retention_ms)

    async def claim(self, store: IdempotencyStore, request: IdempotentRequest) -> ClaimOutcome:
        """Claim the key of a request in the caller's transaction.

        Args:
            store: The store bound to the caller's transaction.
            request: The request and its key.

        Returns:
            `NewRequest` when the write should run, or the response of the first request.

        Raises:
            IdempotencyKeyReusedError: The key was used with a different request.
            DatabaseUnavailableError: The wait for another request with the same key
                exceeded the lock timeout, or the database is not available.
        """
        now = self._clock.now()
        outcome = await store.claim(request, now=now, expired_before=now - self._retention)
        match outcome:
            case NewRequest():
                return outcome
            case ExistingRecord():
                return resolve_existing_record(outcome, request)
            case _:
                assert_never(outcome)
