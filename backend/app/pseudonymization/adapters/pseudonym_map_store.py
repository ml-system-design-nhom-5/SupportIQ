"""The `PseudonymMapStore` port on `pseudonym_map_entries` (ADR-0010, SEC-37)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.persistence import parse_stored_enum
from app.pseudonymization.adapters.tables import PseudonymMapEntryRow
from app.pseudonymization.domain import (
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

    async def insert_map(
        self, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...], created_at: datetime
    ) -> None:
        """Insert the map of a ticket that has none yet; a row stored meanwhile stays.

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

        Raises:
            UnexpectedFailureError: A stored pseudonym type is no value of its enum: a defect.
                The error never holds an original value (SEC-37).
        """
        rows = await self._session.scalars(
            select(PseudonymMapEntryRow)
            .where(PseudonymMapEntryRow.ticket_id == ticket_id)
            .order_by(PseudonymMapEntryRow.pseudonym)
        )
        return tuple(
            PseudonymEntry(
                row.pseudonym,
                parse_stored_enum(PseudonymType, row.pseudonym_type),
                row.original_value,
            )
            for row in rows
        )
