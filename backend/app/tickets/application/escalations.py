"""Escalate a ticket to the manager queue (`createEscalation`, ADR-0006).

The AI only recommends an escalation; this staff action decides it, and records the staff
decision `escalate`. Staff may escalate while a suggestion part is pending. The escalation,
the decision, the ticket's new state, the audit entries, and the idempotency record commit
together.
"""

from collections.abc import Callable, Mapping

from app.accounts import Principal, SupportPrincipal
from app.audit import AuditEventType, AuditValue
from app.idempotency import (
    IdempotencyKey,
    IdempotentRequest,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from app.platform import EventName, OperationId, TransactionRunner
from app.tickets.application.canonical_requests import to_canonical_escalation
from app.tickets.application.console_actions import (
    ActionContext,
    begin_action,
    build_audit_entry,
    build_recorded_decision,
    join_reason_codes,
    load_display_name,
    record_decision_event,
    save_decision,
)
from app.tickets.application.console_ports import (
    ConsolePorts,
    ConsoleStores,
    load_current_suggestion,
)
from app.tickets.domain import (
    ConsoleTicket,
    Escalation,
    EscalationId,
    EscalationRecord,
    EscalationRequest,
    StaffDecision,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
    check_escalation_allowed,
    check_suggestion_is_current,
    derive_escalation_decision,
    validate_escalation_body,
)


class CreateEscalation:
    """Move an `open` ticket to the manager queue (`createEscalation`)."""

    def __init__(
        self,
        transactions: TransactionRunner[ConsoleStores],
        ports: ConsolePorts,
        render_response: Callable[[EscalationRecord], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the escalation.
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
        return self._ports.authorizer.require_staff(principal, OperationId.CREATE_ESCALATION)

    async def execute(
        self,
        support: SupportPrincipal,
        ticket_id: TicketId,
        escalation: EscalationRequest,
        key: IdempotencyKey,
    ) -> StoredResponse:
        """Escalate the ticket, or return the response of the first request with this key.

        Args:
            support: The caller, from `authorize`.
            ticket_id: The ticket.
            escalation: The body of the request, parsed.
            key: The `Idempotency-Key`.

        Returns:
            The `201` response with the escalation.

        Raises:
            TicketNotFoundError: The ticket is unknown.
            IdempotencyKeyReusedError: The key was used with a different request.
            InvalidTicketStateError: The ticket is not `open`.
            SuggestionSupersededError: The body names another suggestion.
            NoteRequiredError: `other` without a note (422).
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        request = _build_request(support, ticket_id, escalation, key)
        self._ports.steps.record_ticket(ticket_id)
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            ticket = await stores.tickets.lock_console_ticket(ticket_id)
            if ticket is None:
                raise TicketNotFoundError
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            _check_escalation(ticket, escalation)
            action = begin_action(self._ports, ticket, support)
            record, decision = await self._escalate(stores, ticket, action, escalation)
            response = self._render_response(record)
            await stores.idempotency.save_response(request, response)
            await transaction.commit()
        self._ports.events.record(EventName.TICKET_ESCALATED, ticket_id=ticket_id)
        record_decision_event(self._ports, ticket_id, decision)
        return response

    async def _escalate(
        self,
        stores: ConsoleStores,
        ticket: ConsoleTicket,
        action: ActionContext,
        request: EscalationRequest,
    ) -> tuple[EscalationRecord, StaffDecision]:
        suggestion = await load_current_suggestion(stores.suggestions, ticket)
        escalation = Escalation(
            escalation_id=EscalationId(self._ports.ids.generate()),
            ticket_id=action.ticket_id,
            request=request,
            escalated_by=action.actor,
            escalated_at=action.acted_at,
        )
        await stores.escalations.insert_escalation(escalation)
        await stores.ticket_states.move_to_manager_queue(action.ticket_id, TicketStatus.ESCALATED)
        await stores.audit.append(
            build_audit_entry(
                self._ports, action, AuditEventType.TICKET_ESCALATED, _escalated_data(escalation)
            )
        )
        decision = derive_escalation_decision(request, suggestion)
        recorded = build_recorded_decision(self._ports, action, decision, None)
        await save_decision(stores, self._ports, recorded)
        return EscalationRecord(escalation, await load_display_name(stores, action.actor)), decision


def _build_request(
    support: SupportPrincipal,
    ticket_id: TicketId,
    escalation: EscalationRequest,
    key: IdempotencyKey,
) -> IdempotentRequest:
    return build_idempotent_request(
        RequesterId(support.account_id),
        OperationId.CREATE_ESCALATION,
        key,
        to_canonical_escalation(ticket_id, escalation),
    )


def _check_escalation(ticket: ConsoleTicket, escalation: EscalationRequest) -> None:
    # Steps 4, 7, and 8 of the check order; a pending part does not matter here (step 6).
    check_escalation_allowed(ticket)
    check_suggestion_is_current(ticket, escalation.suggestion_id)
    validate_escalation_body(escalation)


def _escalated_data(escalation: Escalation) -> Mapping[str, AuditValue]:
    request = escalation.request
    data: dict[str, AuditValue] = {
        "escalation_id": str(escalation.escalation_id),
        "staff_reason_codes": join_reason_codes(request.staff_reason_codes),
    }
    if request.suggestion_id is not None:
        data["suggestion_id"] = request.suggestion_id
    return data
