"""The port of the idempotency records (ERR-15, backend foundation design)."""

from datetime import datetime
from typing import Protocol

from app.idempotency.domain.requests import (
    ExistingRecord,
    IdempotentRequest,
    NewRequest,
    StoredResponse,
)


class IdempotencyStore(Protocol):
    """Keep one record per key, inside the transaction of the write it guards."""

    async def claim(
        self, request: IdempotentRequest, *, now: datetime, expired_before: datetime
    ) -> NewRequest | ExistingRecord:
        """Insert the record of a key without a response, or find the record that exists.

        A record of the same key that another transaction holds makes the call wait until
        that transaction ends, at most the lock timeout. Records created before
        `expired_before` are deleted first, so the table never needs a scheduler.

        Args:
            request: The request and its key.
            now: The creation time of a new record.
            expired_before: Records created before this time are expired.

        Returns:
            `NewRequest` when the record was inserted, or the committed record of the key.

        Raises:
            DatabaseUnavailableError: The wait exceeded the lock timeout, or the database is
                not available.
        """
        ...

    async def save_response(self, request: IdempotentRequest, response: StoredResponse) -> None:
        """Store the response of a successful write in its record, before the commit.

        Args:
            request: The request whose record `claim` inserted.
            response: The response to return to every repeat.
        """
        ...
