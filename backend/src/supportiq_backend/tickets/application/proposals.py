"""Submit a reply proposal for a manager to send (`createReplyProposal`, FR-06).

Staff propose the reply of a ticket that requires authority, or of any other `open` ticket
that they want a manager to review. The proposal moves the ticket to `awaiting_approval` and
never reaches the customer: only `sendReply` writes a reply (FR-04). The proposal, the
ticket's new state, the audit entry, and the idempotency record commit together.
"""

from collections.abc import Callable

from supportiq_backend.accounts import Principal, SupportPrincipal
from supportiq_backend.audit import AuditEventType
from supportiq_backend.idempotency import (
    IdempotencyKey,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import EventName, OperationId, TransactionRunner
from supportiq_backend.tickets.application.canonical_requests import to_canonical_reply
from supportiq_backend.tickets.application.console_actions import (
    build_audit_entry,
)
from supportiq_backend.tickets.application.console_ports import (
    ConsolePorts,
    ConsoleStores,
    load_current_suggestion,
)
from supportiq_backend.tickets.domain import (
    ProposalId,
    ProposalRecord,
    ProposalRequest,
    ReplyProposal,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
    check_proposal_allowed,
    check_suggestion_is_current,
    validate_reply_body,
)


class CreateReplyProposal:
    """Store a reply that staff prepared for a manager to send (`createReplyProposal`)."""

    def __init__(
        self,
        transactions: TransactionRunner[ConsoleStores],
        ports: ConsolePorts,
        render_response: Callable[[ProposalRecord], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the proposal.
            ports: The ports.
            render_response: Writes the `201` response, the one that every repeat of the
                request returns. The interface layer provides it.
        """
        self._transactions = transactions
        self._ports = ports
        self._render_response = render_response

    def authorize(self, principal: Principal) -> SupportPrincipal:
        """Allow only staff, before the request is parsed; a manager sends replies instead.

        Args:
            principal: The caller.

        Returns:
            The caller as a staff member.

        Raises:
            ForbiddenRoleError: The caller is a customer, an admin, or a manager.
        """
        return self._ports.authorizer.require_staff(principal, OperationId.CREATE_REPLY_PROPOSAL)

    async def execute(
        self,
        support: SupportPrincipal,
        ticket_id: TicketId,
        proposal: ProposalRequest,
        key: IdempotencyKey,
    ) -> StoredResponse:
        """Store the proposal, or return the response of the first request with this key.

        Args:
            support: The caller, from `authorize`.
            ticket_id: The ticket.
            proposal: The body of the request, parsed.
            key: The `Idempotency-Key`.

        Returns:
            The `201` response with the proposal.

        Raises:
            TicketNotFoundError: The ticket is unknown.
            IdempotencyKeyReusedError: The key was used with a different request.
            InvalidTicketStateError: The ticket is not `open`.
            SuggestionPendingError: A part of the current suggestion is pending.
            SuggestionSupersededError: The body names another suggestion.
            InvalidRequestError: A body rule of the basis is broken (422).
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        request = build_idempotent_request(
            RequesterId(support.account_id),
            OperationId.CREATE_REPLY_PROPOSAL,
            key,
            to_canonical_reply(ticket_id, proposal),
        )
        self._ports.steps.record_ticket(ticket_id)
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            ticket = await stores.tickets.lock_console_ticket(ticket_id)
            if ticket is None:
                raise TicketNotFoundError
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            suggestion = await load_current_suggestion(stores.suggestions, ticket)
            check_proposal_allowed(ticket, suggestion)
            check_suggestion_is_current(ticket, proposal.suggestion_id)
            validate_reply_body(ticket, suggestion, proposal)
            response = self._render_response(
                await self._submit(stores, ticket_id, support, proposal)
            )
            await stores.idempotency.save_response(request, response)
            await transaction.commit()
        self._ports.events.record(EventName.REPLY_PROPOSAL_SUBMITTED, ticket_id=ticket_id)
        return response

    async def _submit(
        self,
        stores: ConsoleStores,
        ticket_id: TicketId,
        support: SupportPrincipal,
        request: ProposalRequest,
    ) -> ProposalRecord:
        proposal = ReplyProposal(
            proposal_id=ProposalId(self._ports.ids.generate()),
            ticket_id=ticket_id,
            request=request,
            proposed_by=support.account_id,
            created_at=self._ports.clock.now(),
        )
        await stores.proposals.insert_proposal(proposal)
        await stores.tickets.move_to_manager_queue(ticket_id, TicketStatus.AWAITING_APPROVAL)
        await stores.audit.append(
            build_audit_entry(
                self._ports,
                ticket_id,
                support.account_id,
                AuditEventType.REPLY_PROPOSAL_SUBMITTED,
                {"proposal_id": str(proposal.proposal_id), "basis": request.basis.value},
            )
        )
        names = await stores.staff.load_display_names(frozenset({support.account_id}))
        return ProposalRecord(proposal, names[support.account_id])
