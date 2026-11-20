"""Restore the pseudonyms of a ticket in AI text, for staff and managers only (ADR-0010).

This is the second of the two functions of the public API of pseudonymization. The stored
AI text is never changed: only what `/console` reads, and what a sent reply is compared with,
carries the original values. The composition root binds the restorer to the session of the
caller's transaction, so the read sees the same snapshot as the rest of the request.
"""

from app.platform import EventName, EventRecorder
from app.pseudonymization.domain import (
    MapTicketId,
    PseudonymMapStore,
    restore_pseudonyms,
)


class RestorePseudonyms:
    """Replace every pseudonym of a ticket's map by its original value in some texts."""

    def __init__(self, pseudonyms: PseudonymMapStore, events: EventRecorder) -> None:
        """Keep the dependencies.

        Args:
            pseudonyms: The pseudonym map, bound to the caller's transaction.
            events: Where a pseudonym missing from the map is recorded.
        """
        self._pseudonyms = pseudonyms
        self._events = events

    async def restore(self, ticket_id: MapTicketId, texts: tuple[str, ...]) -> tuple[str, ...]:
        """Restore the pseudonyms in each text.

        A mask, or a pseudonym missing from the map, stays as written; a missing pseudonym is
        a defect and is logged once per call as `pseudonym.restore_failed`.

        Args:
            ticket_id: The ticket whose map applies.
            texts: AI texts with placeholders, as stored.

        Returns:
            The restored texts, in the same order. Confidential.

        Raises:
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        if not texts:
            return ()
        entries = await self._pseudonyms.load_entries(ticket_id)
        restored = tuple(restore_pseudonyms(text, entries) for text in texts)
        if any(text.missing_pseudonym_count for text in restored):
            self._events.record(EventName.PSEUDONYM_RESTORE_FAILED, ticket_id=ticket_id)
        return tuple(text.text for text in restored)
