"""The port of the pseudonym map, which only pseudonymization reads or writes (SEC-37)."""

from datetime import datetime
from typing import NewType, Protocol

from app.pseudonymization.domain.pseudonym_map import PseudonymEntry

# The ticket whose message a map belongs to, such as `TCK-1042`. Internal.
MapTicketId = NewType("MapTicketId", str)


class PseudonymMapStore(Protocol):
    """Insert a ticket's map once and read it back; rows are never updated (ADR-0010)."""

    async def insert_map(
        self, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...], created_at: datetime
    ) -> None:
        """Insert the map of a ticket that has none yet.

        A row that a concurrent first run of the same ticket inserted stays as it is, and the
        comparison that follows finds any difference.

        Args:
            ticket_id: The ticket.
            entries: The map computed now.
            created_at: When the run started.
        """
        ...

    async def load_entries(self, ticket_id: MapTicketId) -> tuple[PseudonymEntry, ...]:
        """Load a ticket's map.

        Args:
            ticket_id: The ticket.

        Returns:
            The entries, ordered by pseudonym; empty when there is no map.
        """
        ...
