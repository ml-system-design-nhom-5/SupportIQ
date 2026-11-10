"""Idempotency records in PostgreSQL, guarded by the unique key of the table (ERR-15).

`claim` inserts the record with `ON CONFLICT DO NOTHING`. While another transaction holds an
uncommitted record of the same key, the insert waits on the unique index until it ends, at
most `lock_timeout`; then it either inserts (the other rolled back) or finds the committed
record (backend foundation design, Creating a shop ticket). Expired records are deleted with
`FOR UPDATE SKIP LOCKED`, so cleaning never makes one request wait for another.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    ColumnElement,
    Text,
    and_,
    cast,
    literal,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.idempotency.adapters.tables import IdempotencyRecordRow
from supportiq_backend.idempotency.domain import (
    ExistingRecord,
    IdempotentRequest,
    NewRequest,
    RequestHash,
    StoredResponse,
)
from supportiq_backend.platform import DatabaseUnavailableError
from supportiq_backend.platform.persistence import delete_rows_not_held

_KEY_COLUMNS = (
    IdempotencyRecordRow.account_id,
    IdempotencyRecordRow.operation_id,
    IdempotencyRecordRow.idempotency_key,
)


class PostgresIdempotencyStore:
    """Implement the `IdempotencyStore` port on `idempotency_records`."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def claim(
        self, request: IdempotentRequest, *, now: datetime, expired_before: datetime
    ) -> NewRequest | ExistingRecord:
        """Insert the record of a key, or return the committed record of that key.

        Args:
            request: The request and its key.
            now: The creation time of a new record.
            expired_before: Records created before this time are deleted first.

        Returns:
            `NewRequest` when inserted, or the committed record.

        Raises:
            DatabaseUnavailableError: The record of the key vanished between the conflict and
                the read, which only a concurrent cleanup can cause; a retry succeeds.
        """
        await self._delete_expired(expired_before)
        inserted = await self._session.scalar(
            insert(IdempotencyRecordRow)
            .values(
                account_id=UUID(request.requester_id),
                operation_id=request.operation.value,
                idempotency_key=request.key,
                request_hash=request.request_hash,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=_KEY_COLUMNS)
            .returning(IdempotencyRecordRow.idempotency_key)
        )
        if inserted is not None:
            return NewRequest()
        return await self._load_existing(request)

    async def save_response(self, request: IdempotentRequest, response: StoredResponse) -> None:
        """Store the response of the write in the record of its key.

        Args:
            request: The request whose record `claim` inserted.
            response: The status and the exact body text of the response.
        """
        await self._session.execute(
            update(IdempotencyRecordRow)
            .where(_is_record_of(request))
            .values(
                response_status=response.status_code,
                # A text bound and cast keeps the body exact; a JSON bound would serialize it.
                response_body=cast(literal(response.body, Text()), JSON()),
            )
            .execution_options(synchronize_session=False)
        )

    async def _delete_expired(self, expired_before: datetime) -> None:
        await delete_rows_not_held(
            self._session, IdempotencyRecordRow, IdempotencyRecordRow.created_at < expired_before
        )

    async def _load_existing(self, request: IdempotentRequest) -> ExistingRecord:
        row = (
            await self._session.execute(
                select(
                    IdempotencyRecordRow.request_hash,
                    IdempotencyRecordRow.response_status,
                    # As text: the driver would parse a json value, and lose its exact form.
                    cast(IdempotencyRecordRow.response_body, Text()),
                ).where(_is_record_of(request))
            )
        ).one_or_none()
        if row is None:
            raise DatabaseUnavailableError
        request_hash, status_code, body = row
        response = (
            None if status_code is None or body is None else StoredResponse(status_code, body)
        )
        return ExistingRecord(RequestHash(request_hash), response)


def _is_record_of(request: IdempotentRequest) -> ColumnElement[bool]:
    return and_(
        IdempotencyRecordRow.account_id == UUID(request.requester_id),
        IdempotencyRecordRow.operation_id == request.operation.value,
        IdempotencyRecordRow.idempotency_key == request.key,
    )
