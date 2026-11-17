"""The console's reads: `listConsoleTickets` and `getConsoleTicket`.

Every use case checks the role first, in the application layer (SEC-16), and an admin gets
`403` on every one of them (SEC-41).
"""

from dataclasses import dataclass

from supportiq_backend.accounts import AccountId, Principal, SupportPrincipal
from supportiq_backend.commerce import AddressedOrder, Order
from supportiq_backend.platform import OperationId, TransactionRunner
from supportiq_backend.tickets.application.console_ports import (
    ConsolePorts,
    ConsoleStores,
    load_current_suggestion,
    restore_suggestion,
)
from supportiq_backend.tickets.domain import (
    OTHER_ORDERS_LIMIT,
    ConsoleTicket,
    ConsoleTicketPosition,
    Escalation,
    EscalationRecord,
    ProposalRecord,
    ReplyProposal,
    ReplyRecord,
    SentReply,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
    TicketSummary,
    TicketSummaryPage,
    TicketWorkspace,
    compute_allowed_actions,
)


@dataclass(frozen=True, slots=True, repr=False)
class _StaffActions:
    """What staff and managers did on a ticket, with their display names.

    Attributes:
        proposal: The reply proposal, once submitted.
        escalation: The escalation, once escalated.
        reply: The reply, once sent.
    """

    proposal: ProposalRecord | None
    escalation: EscalationRecord | None
    reply: ReplyRecord | None


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
            actions = await _load_staff_actions(stores, ticket)
        order, other_orders = _split_orders(ticket, orders)
        return TicketWorkspace(
            ticket=ticket,
            # The foreign key of `tickets.customer_id` makes the name always present.
            customer_display_name=names[ticket.customer_id],
            order=order,
            other_orders=other_orders,
            suggestion=restored,
            proposal=actions.proposal,
            escalation=actions.escalation,
            reply=actions.reply,
            allowed_actions=compute_allowed_actions(ticket, suggestion, support.role),
        )


async def _load_staff_actions(stores: ConsoleStores, ticket: ConsoleTicket) -> _StaffActions:
    # An open ticket has no proposal, escalation, or reply yet (the state machine), so the
    # workspace that the console polls while a part is pending reads none of them.
    if ticket.status is TicketStatus.OPEN:
        return _StaffActions(None, None, None)
    proposal = await stores.proposals.load_proposal(ticket.ticket_id)
    escalation = await stores.escalations.load_escalation(ticket.ticket_id)
    reply = await stores.replies.load_reply(ticket.ticket_id)
    names = await stores.staff.load_display_names(_actors_of(proposal, escalation, reply))
    # The foreign keys to `accounts` make the name of every actor present.
    return _StaffActions(
        proposal=(
            None if proposal is None else ProposalRecord(proposal, names[proposal.proposed_by])
        ),
        escalation=(
            None
            if escalation is None
            else EscalationRecord(escalation, names[escalation.escalated_by])
        ),
        reply=None if reply is None else ReplyRecord(reply, names[reply.sent_by]),
    )


def _actors_of(
    proposal: ReplyProposal | None, escalation: Escalation | None, reply: SentReply | None
) -> frozenset[AccountId]:
    actors: set[AccountId] = set()
    if proposal is not None:
        actors.add(proposal.proposed_by)
    if escalation is not None:
        actors.add(escalation.escalated_by)
    if reply is not None:
        actors.add(reply.sent_by)
    return frozenset(actors)


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
