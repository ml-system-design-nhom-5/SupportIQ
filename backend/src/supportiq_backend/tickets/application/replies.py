"""Send the reply of a ticket (`sendReply`): the only code that writes a reply (FR-04).

No reply exists without this staff or manager action, and once a ticket requires authority,
only a manager sends its reply (FR-06). The checks follow the check order of the backend
ticket workflow design; the reply, the decision, the ticket's new state, the audit entries,
and the idempotency record commit together.
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import assert_never

from supportiq_backend.accounts import Principal, SupportPrincipal
from supportiq_backend.audit import (
    ActorAccountId,
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditTicketId,
    AuditValue,
)
from supportiq_backend.idempotency import (
    CanonicalValue,
    IdempotencyKey,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import EventName, OperationId, SpanName, TransactionRunner
from supportiq_backend.suggestions import Suggestion, SuggestionId
from supportiq_backend.tickets.application.console import (
    ConsolePorts,
    ConsoleStores,
    load_current_suggestion,
    restore_suggestion,
)
from supportiq_backend.tickets.domain import (
    AiDraftReply,
    ConsoleTicket,
    DecisionId,
    NoAiDraftReply,
    ProposalId,
    ProposalReply,
    RecordedDecision,
    RejectedAiDraftReply,
    ReplyBasis,
    ReplyId,
    ReplyRecord,
    ReplyRequest,
    SentReply,
    StaffDecision,
    StaffReasonCode,
    TicketId,
    TicketNotFoundError,
    check_reply_allowed,
    check_suggestion_is_current,
    derive_decision,
    validate_reply_body,
)

LIST_SEPARATOR = ","
# `change_ratio` has three decimals, so thousandths hold it exactly.
CHANGE_RATIO_SCALE = 1_000


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
            InvalidRequestError: A body rule of the basis is broken (422).
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        request = build_idempotent_request(
            RequesterId(support.account_id),
            OperationId.SEND_REPLY,
            key,
            to_canonical_reply(ticket_id, reply),
        )
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
                suggestion = await load_current_suggestion(stores.suggestions, ticket)
                check_reply_allowed(ticket, suggestion, support.role)
                check_suggestion_is_current(ticket, _suggestion_id_of(reply))
                validate_reply_body(ticket, suggestion, reply)
                record, decision = await self._send(stores, ticket, suggestion, support, reply)
                response = self._render_response(record)
                await stores.idempotency.save_response(request, response)
                await transaction.commit()
        self._record_events(ticket_id, decision)
        return response

    async def _send(
        self,
        stores: ConsoleStores,
        ticket: ConsoleTicket,
        suggestion: Suggestion | None,
        support: SupportPrincipal,
        reply: ReplyRequest,
    ) -> tuple[ReplyRecord, StaffDecision | None]:
        draft_text = None
        if suggestion is not None and suggestion.ready_draft is not None:
            draft_text = (await restore_suggestion(stores.restorer, suggestion)).draft_text
        decision = derive_decision(reply, suggestion, draft_text)
        sent = _build_sent_reply(
            ReplyId(self._ports.ids.generate()),
            ticket.ticket_id,
            support,
            reply,
            self._ports.clock.now(),
        )
        await stores.replies.insert_reply(sent)
        await stores.tickets.close_ticket(ticket.ticket_id, sent.sent_at)
        await stores.audit.append(
            self._entry(
                ticket.ticket_id,
                support,
                AuditEventType.REPLY_SENT,
                {"reply_id": str(sent.reply_id), "basis": sent.basis.value},
            )
        )
        if decision is not None:
            with self._ports.steps.step(SpanName.SAVE_DECISION):
                await self._save_decision(stores, ticket.ticket_id, support, decision)
        names = await stores.staff.load_display_names(frozenset({support.account_id}))
        return ReplyRecord(sent, names[support.account_id]), decision

    async def _save_decision(
        self,
        stores: ConsoleStores,
        ticket_id: TicketId,
        support: SupportPrincipal,
        decision: StaffDecision,
    ) -> None:
        await stores.replies.insert_decision(
            RecordedDecision(
                decision_id=DecisionId(self._ports.ids.generate()),
                ticket_id=ticket_id,
                decision=decision,
                decided_by=support.account_id,
                proposed_by=None,
                is_proposal_changed=None,
                decided_at=self._ports.clock.now(),
            )
        )
        await stores.audit.append(
            self._entry(
                ticket_id, support, AuditEventType.DECISION_RECORDED, _decision_data(decision)
            )
        )

    def _entry(
        self,
        ticket_id: TicketId,
        support: SupportPrincipal,
        event_type: AuditEventType,
        data: Mapping[str, AuditValue],
    ) -> AuditEntry:
        return AuditEntry(
            entry_id=AuditEntryId(self._ports.ids.generate()),
            occurred_at=self._ports.clock.now(),
            event_type=event_type,
            actor_account_id=ActorAccountId(support.account_id),
            ticket_id=AuditTicketId(ticket_id),
            trace_id=self._ports.traces.current_trace_id(),
            data=data,
        )

    def _record_events(self, ticket_id: TicketId, decision: StaffDecision | None) -> None:
        self._ports.events.record(EventName.REPLY_SENT, ticket_id=ticket_id)
        if decision is not None:
            self._ports.events.record(
                EventName.DECISION_RECORDED,
                ticket_id=ticket_id,
                suggestion_id=decision.suggestion_id,
                decision_type=decision.decision_type.value,
            )


def to_canonical_reply(ticket_id: TicketId, reply: ReplyRequest) -> Mapping[str, CanonicalValue]:
    """Build the canonical form of a reply request, for its idempotency record (ERR-15).

    Args:
        ticket_id: The path parameter.
        reply: The body, parsed.

    Returns:
        The body fields and the path parameter as scalars.
    """
    fields: dict[str, CanonicalValue] = {"ticket_id": ticket_id, "body": reply.body}
    match reply:
        case AiDraftReply():
            fields.update(
                basis=ReplyBasis.AI_DRAFT.value,
                suggestion_id=reply.suggestion_id,
                acknowledged_warning_ids=LIST_SEPARATOR.join(
                    sorted(reply.acknowledged_warning_ids)
                ),
                staff_reason_codes=LIST_SEPARATOR.join(
                    code.value for code in reply.staff_reason_codes
                ),
                note=reply.note or "",
                has_note=reply.note is not None,
            )
        case RejectedAiDraftReply():
            fields.update(
                basis=ReplyBasis.REJECTED_AI_DRAFT.value,
                suggestion_id=reply.suggestion_id,
                staff_reason_codes=LIST_SEPARATOR.join(
                    code.value for code in reply.staff_reason_codes
                ),
                note=reply.note or "",
                has_note=reply.note is not None,
            )
        case NoAiDraftReply():
            fields.update(
                basis=ReplyBasis.NO_AI_DRAFT.value, suggestion_id=reply.suggestion_id or ""
            )
        case ProposalReply():
            fields.update(basis=ReplyBasis.REPLY_PROPOSAL.value, proposal_id=str(reply.proposal_id))
        case _:
            assert_never(reply)
    return fields


def _build_sent_reply(
    reply_id: ReplyId,
    ticket_id: TicketId,
    support: SupportPrincipal,
    reply: ReplyRequest,
    sent_at: datetime,
) -> SentReply:
    acknowledged: tuple[str, ...] = ()
    reason_codes: tuple[StaffReasonCode, ...] = ()
    note: str | None = None
    proposal_id: ProposalId | None = None
    match reply:
        case AiDraftReply():
            basis = ReplyBasis.AI_DRAFT
            acknowledged = tuple(sorted(reply.acknowledged_warning_ids))
            reason_codes, note = reply.staff_reason_codes, reply.note
        case RejectedAiDraftReply():
            basis = ReplyBasis.REJECTED_AI_DRAFT
            reason_codes, note = reply.staff_reason_codes, reply.note
        case NoAiDraftReply():
            basis = ReplyBasis.NO_AI_DRAFT
        case ProposalReply():
            basis, proposal_id = ReplyBasis.REPLY_PROPOSAL, reply.proposal_id
        case _:
            assert_never(reply)
    return SentReply(
        reply_id=reply_id,
        ticket_id=ticket_id,
        basis=basis,
        body=reply.body,
        suggestion_id=_suggestion_id_of(reply),
        proposal_id=proposal_id,
        acknowledged_warning_ids=acknowledged,
        staff_reason_codes=reason_codes,
        note=note,
        sent_by=support.account_id,
        sent_at=sent_at,
    )


def _suggestion_id_of(reply: ReplyRequest) -> SuggestionId | None:
    match reply:
        case AiDraftReply() | RejectedAiDraftReply() | NoAiDraftReply():
            return reply.suggestion_id
        case ProposalReply():
            return None
        case _:
            assert_never(reply)


def _decision_data(decision: StaffDecision) -> Mapping[str, AuditValue]:
    data: dict[str, AuditValue] = {
        "decision_type": decision.decision_type.value,
        "suggestion_id": decision.suggestion_id,
        "staff_reason_codes": LIST_SEPARATOR.join(
            code.value for code in decision.staff_reason_codes
        ),
    }
    if decision.change_ratio is not None:
        # Audit values are scalars without fractions, so the ratio is kept in thousandths.
        data["change_ratio_thousandths"] = round(decision.change_ratio * CHANGE_RATIO_SCALE)
    return data
