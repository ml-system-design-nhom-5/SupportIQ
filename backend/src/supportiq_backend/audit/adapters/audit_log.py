"""The audit log in PostgreSQL: one insert per entry, in the caller's session (SEC-39)."""

from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.audit.adapters.tables import AuditLogEntryRow
from supportiq_backend.audit.domain import AuditEntry


class PostgresAuditLog:
    """Implement the `AuditLog` port on `audit_log_entries`.

    `supportiq_app` may only insert into the table, and a trigger rejects every update and
    delete, so this adapter has no other operation.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the adapter to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def append(self, entry: AuditEntry) -> None:
        """Insert one entry; it commits or rolls back with the transaction.

        Args:
            entry: The entry.
        """
        await self._session.execute(
            insert(AuditLogEntryRow).values(
                entry_id=entry.entry_id,
                occurred_at=entry.occurred_at,
                event_type=entry.event_type.value,
                actor_account_id=_to_uuid(entry.actor_account_id),
                ticket_id=entry.ticket_id,
                trace_id=entry.trace_id,
                data=dict(entry.data),
            )
        )


def _to_uuid(account_id: str | None) -> UUID | None:
    return None if account_id is None else UUID(account_id)
