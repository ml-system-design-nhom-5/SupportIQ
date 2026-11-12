"""The console's reads: `listConsoleTickets` and `getConsoleTicket`, and their stores and ports.

Every use case checks the role first, in the application layer (SEC-16), and an admin gets
`403` on every one of them (SEC-41).
"""

from dataclasses import dataclass

from supportiq_backend.accounts import (
    Authorizer,
    Principal,
    StaffDirectory,
    SupportPrincipal,
)
from supportiq_backend.audit import AuditLog
from supportiq_backend.commerce import AddressedOrder, CustomerRecords, Order
from supportiq_backend.idempotency import (
    IdempotencyGuard,
    IdempotencyStore,
)
from supportiq_backend.platform import (
    Clock,
    EventRecorder,
    IdGenerator,
    OperationId,
    StepTracer,
    TraceContext,
    TransactionRunner,
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
    OTHER_ORDERS_LIMIT,
    ConsoleTicket,
    ConsoleTicketPosition,
    ConsoleTicketStore,
    HandlingMode,
    ReplyRecord,
    ReplyStore,
    RestoredSuggestion,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
    TicketSummary,
    TicketSummaryPage,
    TicketWorkspace,
    build_draft_text,
    compute_allowed_actions,
)


@dataclass(frozen=True, slots=True)
class ConsoleStores:
    """The stores of the console use cases, all in one transaction.

    Attributes:
        tickets: The tickets and their messages.
        replies: The replies and staff decisions.
        suggestions: The suggestions.
        links: The ticket rows that suggestions reads and links.
        records: The customers' commerce records, read-only.
        staff: The display names of staff and managers.
        restorer: Restores pseudonyms in AI text, in this transaction.
        idempotency: The idempotency records.
        audit: The audit log.
    """

    tickets: ConsoleTicketStore
    replies: ReplyStore
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


class ListConsoleTickets:
    """Return one page of the tickets in one status (`listConsoleTickets`)."""

    def __init__(self, transactions: TransactionRunner[ConsoleStores], ports: ConsolePorts) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the read transaction.
            ports: The ports.
        """
        self._transactions = transactions
        self._ports = ports

    def authorize(self, principal: Principal) -> SupportPrincipal:
        """Allow only staff and managers, before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a member of support.

        Raises:
            ForbiddenRoleError: The caller is a customer or an admin.
        """
        return self._ports.authorizer.require_support(principal, OperationId.LIST_CONSOLE_TICKETS)

    async def execute(
        self,
        support: SupportPrincipal,
        status: TicketStatus,
        after: ConsoleTicketPosition | None,
        limit: int,
    ) -> TicketSummaryPage:
        """Load one page of a queue.

        Args:
            support: The caller, from `authorize`.
            status: The queue; staff may ask for `open` only.
            after: The last ticket of the previous page, or None for the first page.
            limit: The maximum number of tickets.

        Returns:
            The page.

        Raises:
            ForbiddenRoleError: Staff asked for another queue than `open`.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        if status is not TicketStatus.OPEN:
            self._ports.authorizer.require_manager(support, OperationId.LIST_CONSOLE_TICKETS)
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            tickets = await stores.tickets.load_console_tickets(
                status, after=after, limit=limit + 1
            )
            page = tickets[:limit]
            names = await stores.records.load_display_names(
                frozenset(ticket.customer_id for ticket in page)
            )
            suggestions = await stores.suggestions.load_suggestions(
                frozenset(
                    ticket.current_suggestion_id
                    for ticket in page
                    if ticket.current_suggestion_id is not None
                )
            )
        items = tuple(
            TicketSummary(
                ticket,
                names[ticket.customer_id],
                None
                if ticket.current_suggestion_id is None
                else suggestions.get(ticket.current_suggestion_id),
            )
            for ticket in page
        )
        return TicketSummaryPage(items, _next_position(status, page, has_more=len(tickets) > limit))


class GetConsoleTicket:
    """Return the workspace of one ticket (`getConsoleTicket`). It changes nothing."""

    def __init__(self, transactions: TransactionRunner[ConsoleStores], ports: ConsolePorts) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the read transaction.
            ports: The ports.
        """
        self._transactions = transactions
        self._ports = ports

    async def execute(self, principal: Principal, ticket_id: TicketId) -> TicketWorkspace:
        """Load the workspace, with the pseudonyms of the AI text restored (ADR-0010).

        Args:
            principal: The caller.
            ticket_id: The ticket.

        Returns:
            The workspace.

        Raises:
            ForbiddenRoleError: The caller is a customer or an admin.
            TicketNotFoundError: The ticket is unknown.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        support = self._ports.authorizer.require_support(principal, OperationId.GET_CONSOLE_TICKET)
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            ticket = await stores.tickets.load_console_ticket(ticket_id)
            if ticket is None:
                raise TicketNotFoundError
            suggestion = await load_current_suggestion(stores.suggestions, ticket)
            restored = (
                None
                if suggestion is None
                else await restore_suggestion(stores.restorer, suggestion)
            )
            names = await stores.records.load_display_names(frozenset({ticket.customer_id}))
            orders = await stores.records.load_addressed_orders(
                ticket.customer_id, ticket.order_id, OTHER_ORDERS_LIMIT
            )
            reply = await self._load_reply(stores, ticket)
        order, other_orders = _split_orders(ticket, orders)
        return TicketWorkspace(
            ticket=ticket,
            # The foreign key of `tickets.customer_id` makes the name always present.
            customer_display_name=names[ticket.customer_id],
            order=order,
            other_orders=other_orders,
            suggestion=restored,
            reply=reply,
            allowed_actions=compute_allowed_actions(ticket, suggestion, support.role),
        )

    async def _load_reply(self, stores: ConsoleStores, ticket: ConsoleTicket) -> ReplyRecord | None:
        reply = await stores.replies.load_reply(ticket.ticket_id)
        if reply is None:
            return None
        names = await stores.staff.load_display_names(frozenset({reply.sent_by}))
        # The foreign key of `replies.sent_by_account_id` makes the name always present.
        return ReplyRecord(reply, names[reply.sent_by])


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


def _split_orders(
    ticket: ConsoleTicket, orders: tuple[AddressedOrder, ...]
) -> tuple[AddressedOrder | None, tuple[Order, ...]]:
    order = next((item for item in orders if item.order.order_id == ticket.order_id), None)
    return order, tuple(item.order for item in orders if item.order.order_id != ticket.order_id)


def _next_position(
    status: TicketStatus, page: tuple[ConsoleTicket, ...], *, has_more: bool
) -> ConsoleTicketPosition | None:
    if not has_more or not page:
        return None
    last = page[-1]
    moment = last.closed_at if status is TicketStatus.CLOSED else last.created_at
    if moment is None:
        return None
    return ConsoleTicketPosition(status, moment, last.ticket_id)
