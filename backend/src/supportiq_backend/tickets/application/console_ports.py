"""The stores and ports of the console use cases, and the reads that several of them share."""

from dataclasses import dataclass

from supportiq_backend.accounts import Authorizer, StaffDirectory
from supportiq_backend.audit import AuditLog
from supportiq_backend.commerce import CustomerRecords
from supportiq_backend.idempotency import IdempotencyGuard, IdempotencyStore
from supportiq_backend.platform import (
    Clock,
    EventRecorder,
    IdGenerator,
    StepTracer,
    TraceContext,
)
from supportiq_backend.pseudonymization import MapTicketId
from supportiq_backend.suggestions import (
    AiService,
    DraftReady,
    PseudonymRestorer,
    Suggestion,
    SuggestionStarter,
    SuggestionStore,
    SuggestionTickets,
)
from supportiq_backend.tickets.domain import (
    ConsoleTicket,
    ConsoleTicketStore,
    EscalationStore,
    HandlingMode,
    ReplyProposalStore,
    ReplyStore,
    RestoredSuggestion,
    TicketStateStore,
    build_draft_text,
)


@dataclass(frozen=True, slots=True)
class ConsoleStores:
    """The stores of the console use cases, all in one transaction.

    Attributes:
        tickets: The tickets and their messages.
        ticket_states: The state of a locked ticket: its handling clock, queue, and closing.
        replies: The replies and staff decisions.
        proposals: The reply proposals.
        escalations: The escalations.
        suggestions: The suggestions.
        links: The ticket rows that suggestions reads and links.
        records: The customers' commerce records, read-only.
        staff: The display names of staff and managers.
        restorer: Restores pseudonyms in AI text, in this transaction.
        idempotency: The idempotency records.
        audit: The audit log.
    """

    tickets: ConsoleTicketStore
    ticket_states: TicketStateStore
    replies: ReplyStore
    proposals: ReplyProposalStore
    escalations: EscalationStore
    suggestions: SuggestionStore
    links: SuggestionTickets
    records: CustomerRecords
    staff: StaffDirectory
    restorer: PseudonymRestorer
    idempotency: IdempotencyStore
    audit: AuditLog


@dataclass(frozen=True, slots=True)
class ConsolePorts:
    """The ports of the console use cases besides their stores.

    Attributes:
        authorizer: The role checks.
        guard: The idempotency guard.
        clock: The clock.
        ids: Generates the IDs of new records.
        traces: Tells the trace of the request.
        events: Where events are recorded.
        steps: Runs a step in its span.
        starter: Starts suggestions.
        ai_service: The client of ai-service, for the KB version of a first view.
    """

    authorizer: Authorizer
    guard: IdempotencyGuard
    clock: Clock
    ids: IdGenerator
    traces: TraceContext
    events: EventRecorder
    steps: StepTracer
    starter: SuggestionStarter
    ai_service: AiService


async def load_current_suggestion(
    suggestions: SuggestionStore, ticket: ConsoleTicket
) -> Suggestion | None:
    """Load the current suggestion of a ticket in assisted mode.

    Args:
        suggestions: The suggestion store of the transaction.
        ticket: The ticket.

    Returns:
        The suggestion, or None in manual mode or before the first one.
    """
    if ticket.handling_mode is HandlingMode.MANUAL or ticket.current_suggestion_id is None:
        return None
    return await suggestions.load_suggestion(ticket.current_suggestion_id)


async def restore_suggestion(
    restorer: PseudonymRestorer, suggestion: Suggestion
) -> RestoredSuggestion:
    """Restore the pseudonyms of a suggestion's draft and staff note (ADR-0010).

    Args:
        restorer: Restores pseudonyms in the caller's transaction.
        suggestion: The suggestion as stored.

    Returns:
        The suggestion with its restored texts and the canonical draft text.
    """
    draft = suggestion.ready_draft
    segments = () if draft is None else draft.draft.segments
    note = suggestion.staff_note
    texts = (*(segment.text for segment in segments), *(() if note is None else (note,)))
    restored = await restorer.restore(MapTicketId(suggestion.ticket_id), texts)
    segment_texts = restored[: len(segments)]
    return RestoredSuggestion(
        suggestion=suggestion,
        segment_texts=segment_texts,
        draft_text=_draft_text(draft, segment_texts),
        staff_note=None if note is None else restored[len(segments)],
    )


def _draft_text(draft: DraftReady | None, segment_texts: tuple[str, ...]) -> str | None:
    if draft is None:
        return None
    return build_draft_text(
        tuple(
            (segment.paragraph_index, text)
            for segment, text in zip(draft.draft.segments, segment_texts, strict=True)
        )
    )
