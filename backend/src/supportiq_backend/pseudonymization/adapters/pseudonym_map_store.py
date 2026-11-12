"""The `PseudonymMapStore` port on `pseudonym_map_entries` (ADR-0010, SEC-37)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.pseudonymization.adapters.tables import PseudonymMapEntryRow
from supportiq_backend.pseudonymization.domain import (
    MapTicketId,
    PseudonymEntry,
    PseudonymType,
)


class PostgresPseudonymMapStore:
    """Insert a ticket's map once and read it back, in the transaction of one session.

    `supportiq_app` may only select and insert rows of the table, so no row is ever updated
    or deleted by the replicas.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def insert_missing(
        self, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...], created_at: datetime
    ) -> None:
        """Insert the entries that the ticket's map does not hold yet.

        Args:
            ticket_id: The ticket.
            entries: The map computed now.
            created_at: When the run started.
        """
        if not entries:
            return
        await self._session.execute(
            insert(PseudonymMapEntryRow)
            .values(
                [
                    {
                        "ticket_id": ticket_id,
                        "pseudonym": entry.pseudonym,
                        "pseudonym_type": entry.pseudonym_type.value,
                        "original_value": entry.original_value,
                        "created_at": created_at,
                    }
                    for entry in entries
                ]
            )
            .on_conflict_do_nothing(index_elements=["ticket_id", "pseudonym"])
        )

    async def load_entries(self, ticket_id: MapTicketId) -> tuple[PseudonymEntry, ...]:
        """Load a ticket's map.

        Args:
            ticket_id: The ticket.

        Returns:
            The entries, ordered by pseudonym; empty when there is no map.
        """
        rows = await self._session.scalars(
            select(PseudonymMapEntryRow)
            .where(PseudonymMapEntryRow.ticket_id == ticket_id)
            .order_by(PseudonymMapEntryRow.pseudonym)
        )
        return tuple(
            PseudonymEntry(row.pseudonym, PseudonymType(row.pseudonym_type), row.original_value)
            for row in rows
        )
