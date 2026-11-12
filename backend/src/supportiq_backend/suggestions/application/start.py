"""Start a suggestion inside the caller's transaction (backend ticket workflow design, item 1).

Ticket creation, a view, and `createSuggestion` all start suggestions the same way: the
previous suggestion's pending parts become `cancelled` and its job ends, the new suggestion
gets two pending parts and a queued job, and it becomes the ticket's current suggestion, all
in the caller's transaction. After the commit the caller announces it, which wakes the claim
loop of this replica.
"""

from dataclasses import dataclass

from supportiq_backend.accounts import AccountId
from supportiq_backend.platform import Clock, EventName, EventRecorder, IdGenerator, TraceContext
from supportiq_backend.suggestions.domain import (
    IntentLabel,
    NewSuggestion,
    SuggestionId,
    SuggestionQueue,
    SuggestionStore,
    SuggestionTicketId,
    SuggestionTickets,
    SuggestionTrigger,
)


@dataclass(frozen=True, slots=True)
class SuggestionStart:
    """What a new suggestion carries.

    Attributes:
        ticket_id: The ticket, locked or just inserted by the caller's transaction.
        trigger: Why it is created.
        intent_override: The intent that staff chose; a retry repeats the failed one's.
        requested_by: The account that asked; absent for `ticket_created`.
    """

    ticket_id: SuggestionTicketId
    trigger: SuggestionTrigger
    intent_override: IntentLabel | None
    requested_by: AccountId | None


@dataclass(frozen=True, slots=True)
class StartedSuggestion:
    """A suggestion inserted by a transaction that has not committed yet.

    Attributes:
        suggestion: The new suggestion.
        superseded_ids: The suggestions whose pending parts it cancelled.
    """

    suggestion: NewSuggestion
    superseded_ids: tuple[SuggestionId, ...]


@dataclass(frozen=True, slots=True)
class SuggestionStarterPorts:
    """The ports of the starter.

    Attributes:
        clock: The clock.
        ids: Generates suggestion IDs.
        traces: Tells the trace of the request, which the suggestion keeps (LOG-04).
        events: Where events are recorded.
        queue: The claim loop of this replica.
    """

    clock: Clock
    ids: IdGenerator
    traces: TraceContext
    events: EventRecorder
    queue: SuggestionQueue


class SuggestionStarter:
    """Insert a suggestion, supersede the previous one, and wake the claim loop after commit."""

    def __init__(self, ports: SuggestionStarterPorts) -> None:
        """Keep the ports.

        Args:
            ports: The ports.
        """
        self._ports = ports

    async def start(
        self, suggestions: SuggestionStore, tickets: SuggestionTickets, start: SuggestionStart
    ) -> StartedSuggestion:
        """Insert the suggestion in the caller's transaction.

        Args:
            suggestions: The suggestion store of the transaction.
            tickets: The ticket rows of the transaction.
            start: What the suggestion carries.

        Returns:
            The suggestion, to announce once the transaction committed.
        """
        now = self._ports.clock.now()
        superseded_ids = await suggestions.cancel_pending_suggestions(start.ticket_id, now)
        suggestion = NewSuggestion(
            suggestion_id=SuggestionId(str(self._ports.ids.generate())),
            ticket_id=start.ticket_id,
            trigger=start.trigger,
            intent_override=start.intent_override,
            requested_by=start.requested_by,
            created_at=now,
            trace_id=self._ports.traces.current_trace_id(),
        )
        await suggestions.insert_suggestion(suggestion)
        await tickets.set_current_suggestion(start.ticket_id, suggestion.suggestion_id)
        return StartedSuggestion(suggestion, superseded_ids)

    def announce(self, started: StartedSuggestion) -> None:
        """Record the events of a committed suggestion and wake the claim loop.

        Args:
            started: The suggestion, committed already.
        """
        suggestion = started.suggestion
        for superseded_id in started.superseded_ids:
            self._ports.events.record(
                EventName.SUGGESTION_SUPERSEDED,
                ticket_id=suggestion.ticket_id,
                suggestion_id=superseded_id,
            )
        self._ports.events.record(
            EventName.SUGGESTION_REQUESTED,
            ticket_id=suggestion.ticket_id,
            suggestion_id=suggestion.suggestion_id,
            suggestion_trigger=suggestion.trigger.value,
        )
        self._ports.queue.notify_new_suggestion(suggestion.ticket_id, suggestion.suggestion_id)
