"""Send the reply of a ticket (`sendReply`): the only code that writes a reply (FR-04).

No reply exists without this staff or manager action, and once a ticket requires authority,
only a manager sends its reply (FR-06). A manager sends a reply proposal with the basis
`reply_proposal`, and the decision of the proposal's basis is recorded then, with both
accounts. The checks follow the check order of the backend ticket workflow design; the reply,
the decision, the ticket's new state, the audit entries, and the idempotency record commit
together.
"""

from collections.abc import Callable, Mapping
from typing import assert_never

from supportiq_backend.accounts import Principal, SupportPrincipal, SupportRole
from supportiq_backend.audit import AuditEventType, AuditValue
from supportiq_backend.idempotency import (
    IdempotencyKey,
    IdempotentRequest,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import EventName, OperationId, SpanName, TransactionRunner
from supportiq_backend.suggestions import Suggestion, SuggestionId
from supportiq_backend.tickets.application.canonical_requests import to_canonical_reply
from supportiq_backend.tickets.application.console_actions import (
    ActionContext,
    begin_action,
    build_audit_entry,
    build_recorded_decision,
    load_display_name,
    record_decision_event,
    save_decision,
)
from supportiq_backend.tickets.application.console_ports import (
    ConsolePorts,
    ConsoleStores,
    load_current_suggestion,
    restore_suggestion,
)
from supportiq_backend.tickets.domain import (
    AiDraftReply,
    ConsoleTicket,
    NoAiDraftReply,
    ProposalReply,
    ProposalRequest,
    RejectedAiDraftReply,
    ReplyBasis,
    ReplyId,
    ReplyRecord,
    ReplyRequest,
    ResolvedReply,
    SentProposal,
    SentReply,
    StaffDecision,
    TicketId,
    TicketNotFoundError,
    check_reply_allowed,
    check_suggestion_is_current,
    derive_decision,
    parse_sent_proposal,
    validate_reply_body,
)


class SendReply:
    """Send a reply to the customer and close the ticket (`sendReply`)."""

    def __init__(
        self,
        transactions: TransactionRunner[ConsoleStores],
        ports: ConsolePorts,
        render_response: Callable[[ReplyRecord], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the reply.
            ports: The ports.
            render_response: Writes the `201` response, the one that every repeat of the
                request returns. The interface layer provides it.
        """
        self._transactions = transactions
        self._ports = ports
        self._render_response = render_response

    def authorize(self, principal: Principal) -> SupportPrincipal:
        """Allow only staff and managers, before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a member of support.

        Raises:
            ForbiddenRoleError: The caller is a customer or an admin.
        """
        return self._ports.authorizer.require_support(principal, OperationId.SEND_REPLY)

    async def execute(
        self,
        support: SupportPrincipal,
        ticket_id: TicketId,
        reply: ReplyRequest,
        key: IdempotencyKey,
    ) -> StoredResponse:
        """Send the reply, or return the response of the first request with this key.

        Args:
            support: The caller.
            ticket_id: The ticket.
            reply: The body of the request, parsed.
            key: The `Idempotency-Key`.

        Returns:
            The `201` response with the reply.

        Raises:
            TicketNotFoundError: The ticket is unknown.
            IdempotencyKeyReusedError: The key was used with a different request.
            InvalidTicketStateError: The ticket is `closed`.
            ForbiddenRoleError: Staff on a ticket that is not `open`.
            AuthorityRequiredError: Staff on a ticket that requires authority (FR-06).
            SuggestionPendingError: A part of the current suggestion is pending.
            SuggestionSupersededError: The body names another suggestion.
            InvalidRequestError: A body rule of the basis is broken, such as a `proposal_id`
                that is not the ticket's proposal (422).
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        request = _build_request(support, ticket_id, reply, key)
        with self._ports.steps.step(SpanName.SEND_REPLY):
            self._ports.steps.record_ticket(ticket_id)
            async with self._transactions.begin() as transaction:
                stores = transaction.stores
                ticket = await stores.tickets.lock_console_ticket(ticket_id)
                if ticket is None:
                    raise TicketNotFoundError
                claim = await self._ports.guard.claim(stores.idempotency, request)
                if isinstance(claim, RepeatedRequest):
                    return claim.response
                suggestion, resolved = await _check_reply(stores, ticket, support.role, reply)
                action = begin_action(self._ports, ticket, support)
                record, decision = await self._send(stores, action, suggestion, resolved)
                response = self._render_response(record)
                await stores.idempotency.save_response(request, response)
                await transaction.commit()
        self._record_events(ticket_id, decision)
        return response

    async def _send(
        self,
        stores: ConsoleStores,
        action: ActionContext,
        suggestion: Suggestion | None,
        reply: ResolvedReply,
    ) -> tuple[ReplyRecord, StaffDecision | None]:
        draft_text = await _restored_draft_text(stores, suggestion)
        decision = derive_decision(reply, suggestion, draft_text)
        sent = _build_sent_reply(ReplyId(self._ports.ids.generate()), action, reply)
        await stores.replies.insert_reply(sent)
        await stores.ticket_states.close_ticket(action.ticket_id, action.acted_at)
        await stores.audit.append(
            build_audit_entry(
                self._ports, action, AuditEventType.REPLY_SENT, _reply_sent_data(sent, reply)
            )
        )
        if decision is not None:
            sent_proposal = reply if isinstance(reply, SentProposal) else None
            recorded = build_recorded_decision(self._ports, action, decision, sent_proposal)
            await save_decision(stores, self._ports, recorded)
        return ReplyRecord(sent, await load_display_name(stores, action.actor)), decision

    def _record_events(self, ticket_id: TicketId, decision: StaffDecision | None) -> None:
        self._ports.events.record(EventName.REPLY_SENT, ticket_id=ticket_id)
        if decision is not None:
            record_decision_event(self._ports, ticket_id, decision)


def _build_request(
    support: SupportPrincipal, ticket_id: TicketId, reply: ReplyRequest, key: IdempotencyKey
) -> IdempotentRequest:
    return build_idempotent_request(
        RequesterId(support.account_id),
        OperationId.SEND_REPLY,
        key,
        to_canonical_reply(ticket_id, reply),
    )


async def _check_reply(
    stores: ConsoleStores, ticket: ConsoleTicket, role: SupportRole, reply: ReplyRequest
) -> tuple[Suggestion | None, ResolvedReply]:
    # Steps 4 to 8 of the check order, after the lock and the idempotency claim.
    suggestion = await load_current_suggestion(stores.suggestions, ticket)
    check_reply_allowed(ticket, suggestion, role)
    check_suggestion_is_current(ticket, _suggestion_id_of(reply))
    resolved = await _resolve_proposal(stores, ticket, reply)
    validate_reply_body(ticket, suggestion, resolved)
    return suggestion, resolved


async def _resolve_proposal(
    stores: ConsoleStores, ticket: ConsoleTicket, reply: ReplyRequest
) -> ResolvedReply:
    match reply:
        case ProposalReply():
            proposal = await stores.proposals.load_proposal(ticket.ticket_id)
            return parse_sent_proposal(reply, proposal)
        case AiDraftReply() | RejectedAiDraftReply() | NoAiDraftReply():
            return reply
        case _:
            assert_never(reply)


async def _restored_draft_text(stores: ConsoleStores, suggestion: Suggestion | None) -> str | None:
    # The decision compares the body with the draft that staff read: its restored text.
    if suggestion is None or suggestion.ready_draft is None:
        return None
    return (await restore_suggestion(stores.restorer, suggestion)).draft_text


def _build_sent_reply(reply_id: ReplyId, action: ActionContext, reply: ResolvedReply) -> SentReply:
    match reply:
        case SentProposal():
            return _build_reply_from_proposal(reply_id, action, reply)
        case AiDraftReply() | RejectedAiDraftReply() | NoAiDraftReply():
            return _build_reply_on_its_basis(reply_id, action, reply)
        case _:
            assert_never(reply)


def _build_reply_from_proposal(
    reply_id: ReplyId, action: ActionContext, sent: SentProposal
) -> SentReply:
    # The acknowledgments, reason codes, and note of staff stay in the proposal that the reply
    # names; the reply holds what the manager's request carried.
    return SentReply(
        reply_id=reply_id,
        ticket_id=action.ticket_id,
        basis=ReplyBasis.REPLY_PROPOSAL,
        body=sent.body,
        suggestion_id=sent.proposal.request.suggestion_id,
        proposal_id=sent.proposal.proposal_id,
        acknowledged_warning_ids=(),
        staff_reason_codes=(),
        note=None,
        sent_by=action.actor,
        sent_at=action.acted_at,
    )


def _build_reply_on_its_basis(
    reply_id: ReplyId, action: ActionContext, reply: ProposalRequest
) -> SentReply:
    return SentReply(
        reply_id=reply_id,
        ticket_id=action.ticket_id,
        basis=reply.basis,
        body=reply.body,
        suggestion_id=reply.suggestion_id,
        proposal_id=None,
        acknowledged_warning_ids=tuple(sorted(reply.acknowledged_warning_ids)),
        staff_reason_codes=reply.staff_reason_codes,
        note=reply.note,
        sent_by=action.actor,
        sent_at=action.acted_at,
    )


def _suggestion_id_of(reply: ReplyRequest) -> SuggestionId | None:
    match reply:
        case AiDraftReply() | RejectedAiDraftReply() | NoAiDraftReply():
            return reply.suggestion_id
        case ProposalReply():
            return None
        case _:
            assert_never(reply)


def _reply_sent_data(sent: SentReply, reply: ResolvedReply) -> Mapping[str, AuditValue]:
    data: dict[str, AuditValue] = {"reply_id": str(sent.reply_id), "basis": sent.basis.value}
    if isinstance(reply, SentProposal):
        # A reply from a proposal names its proposer too (contracts v1 design, Audit log).
        data["proposed_by_account_id"] = reply.proposal.proposed_by
    return data
