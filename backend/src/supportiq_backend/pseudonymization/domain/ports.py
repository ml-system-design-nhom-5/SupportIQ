"""The port of the pseudonym map, which only pseudonymization reads or writes (SEC-37)."""

from datetime import datetime
from typing import NewType, Protocol

from supportiq_backend.pseudonymization.domain.pseudonym_map import PseudonymEntry

# The ticket whose message a map belongs to, such as `TCK-1042`. Internal.
MapTicketId = NewType("MapTicketId", str)


class PseudonymMapStore(Protocol):
    """Insert a ticket's map once and read it back; rows are never updated (ADR-0010)."""

    async def insert_missing(
        self, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...], created_at: datetime
    ) -> None:
        """Insert the entries that the ticket's map does not hold yet.

        A row that already exists stays as it is, so two jobs of one ticket that pseudonymize
        at the same time both succeed, and the comparison that follows finds any difference.

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
            The entries, ordered by pseudonym type and number; empty when there is no map.
        """
        ...
