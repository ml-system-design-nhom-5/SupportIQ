"""Correct the intent or retry the AI (`createSuggestion`, contracts v1 design).

The checks follow the check order of the backend ticket workflow design: the role, the
ticket, the `Idempotency-Key`, the ticket state and handling mode, and then the rules of an
intent correction or a retry. The new suggestion supersedes the current one, and the
authority flag stays as it is.
"""

from collections.abc import Callable
from dataclasses import dataclass

from supportiq_backend.accounts import Authorizer, Principal, SupportPrincipal
from supportiq_backend.audit import (
    ActorAccountId,
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditLog,
    AuditTicketId,
    AuditValue,
)
from supportiq_backend.idempotency import (
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyStore,
    IdempotentRequest,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import (
    Clock,
    EventName,
    EventRecorder,
    IdGenerator,
    OperationId,
    ResourceNotFoundError,
    TraceContext,
    TransactionRunner,
    UnexpectedFailureError,
)
from supportiq_backend.suggestions.application.start import (
    StartedSuggestion,
    SuggestionStart,
    SuggestionStarter,
)
from supportiq_backend.suggestions.domain import (
    MANUAL_MODE_STATE,
    IntentLabel,
    InvalidTicketStateError,
    NewSuggestion,
    Suggestion,
    SuggestionStore,
    SuggestionTicketId,
    SuggestionTickets,
    SuggestionTrigger,
    TicketForSuggestion,
    plan_requested_suggestion,
)

TICKET_ID_FIELD = "ticket_id"
INTENT_OVERRIDE_FIELD = "intent_override"


@dataclass(frozen=True, slots=True)
class CreateSuggestionStores:
    """The stores of `createSuggestion`, all in one transaction.

    Attributes:
        suggestions: The suggestions.
        links: The ticket rows, locked first.
        idempotency: The idempotency records.
        audit: The audit log.
    """

    suggestions: SuggestionStore
    links: SuggestionTickets
    idempotency: IdempotencyStore
    audit: AuditLog


@dataclass(frozen=True, slots=True)
class CreateSuggestionPorts:
    """The ports of `createSuggestion` besides its stores.

    Attributes:
        authorizer: The role checks.
        guard: The idempotency guard.
        starter: Starts the suggestion.
        clock: The clock.
        ids: Generates the IDs of audit log entries.
        traces: Tells the trace of the request.
        events: Where events are recorded.
    """

    authorizer: Authorizer
    guard: IdempotencyGuard
    starter: SuggestionStarter
    clock: Clock
    ids: IdGenerator
    traces: TraceContext
    events: EventRecorder


class CreateSuggestion:
    """Start a suggestion with an intent override, or as a retry (`createSuggestion`)."""

    def __init__(
        self,
        transactions: TransactionRunner[CreateSuggestionStores],
        ports: CreateSuggestionPorts,
        render_response: Callable[[Suggestion], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the request.
            ports: The ports besides the stores.
            render_response: Writes the `202` response, the one that every repeat returns.
                The interface layer provides it.
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
        return self._ports.authorizer.require_support(principal, OperationId.CREATE_SUGGESTION)

    async def execute(
        self,
        support: SupportPrincipal,
        ticket_id: SuggestionTicketId,
        intent_override: IntentLabel | None,
        key: IdempotencyKey,
    ) -> StoredResponse:
        """Start the suggestion, or return the response of the first request with this key.

        Args:
            support: The caller.
            ticket_id: The ticket.
            intent_override: The intent that staff chose, or None for a retry.
            key: The `Idempotency-Key`.

        Returns:
            The `202` response with the new, pending suggestion.

        Raises:
            ResourceNotFoundError: The ticket is unknown.
            IdempotencyKeyReusedError: The key was used with a different request.
            InvalidTicketStateError: The ticket is not `open`, or in manual mode.
            SuggestionPendingError: An intent correction while no intent is known yet.
            NoIntentKnownError: An intent correction while no intent is known.
            NothingToRetryError: A retry while nothing can be retried.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        request = _build_request(support, ticket_id, intent_override, key)
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            ticket = await stores.links.lock_ticket(ticket_id)
            if ticket is None:
                raise ResourceNotFoundError
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            started, response = await self._start(
                stores, support, ticket_id, ticket, intent_override
            )
            await stores.idempotency.save_response(request, response)
            await transaction.commit()
        self._ports.starter.announce(started)
        if started.suggestion.trigger is SuggestionTrigger.INTENT_OVERRIDE:
            self._ports.events.record(
                EventName.INTENT_OVERRIDDEN,
                ticket_id=ticket_id,
                suggestion_id=started.suggestion.suggestion_id,
            )
        return response

    async def _start(
        self,
        stores: CreateSuggestionStores,
        support: SupportPrincipal,
        ticket_id: SuggestionTicketId,
        ticket: TicketForSuggestion,
        intent_override: IntentLabel | None,
    ) -> tuple[StartedSuggestion, StoredResponse]:
        _check_ticket_state(ticket)
        current = (
            None
            if ticket.current_suggestion_id is None
            else await stores.suggestions.load_suggestion(ticket.current_suggestion_id)
        )
        trigger, override = plan_requested_suggestion(current, intent_override)
        started = await self._ports.starter.start(
            stores.suggestions,
            stores.links,
            SuggestionStart(ticket_id, trigger, override, support.account_id),
        )
        if trigger is SuggestionTrigger.INTENT_OVERRIDE:
            await stores.audit.append(self._override_entry(support, current, started.suggestion))
        created = await stores.suggestions.load_suggestion(started.suggestion.suggestion_id)
        if created is None:
            raise UnexpectedFailureError
        return started, self._render_response(created)

    def _override_entry(
        self, support: SupportPrincipal, current: Suggestion | None, new: NewSuggestion
    ) -> AuditEntry:
        # The chosen intent and the one it replaces: the model's prediction, or an earlier
        # choice of staff (contracts v1 design, Audit log).
        data: dict[str, AuditValue] = {"suggestion_id": new.suggestion_id}
        if new.intent_override is not None:
            data["chosen_intent"] = new.intent_override.value
        previous = None if current is None else current.known_intent
        if previous is not None:
            data["previous_intent"] = previous.value
        return AuditEntry(
            entry_id=AuditEntryId(self._ports.ids.generate()),
            occurred_at=self._ports.clock.now(),
            event_type=AuditEventType.INTENT_OVERRIDDEN,
            actor_account_id=ActorAccountId(support.account_id),
            ticket_id=AuditTicketId(new.ticket_id),
            trace_id=self._ports.traces.current_trace_id(),
            data=data,
        )


def _build_request(
    support: SupportPrincipal,
    ticket_id: SuggestionTicketId,
    intent_override: IntentLabel | None,
    key: IdempotencyKey,
) -> IdempotentRequest:
    return build_idempotent_request(
        RequesterId(support.account_id),
        OperationId.CREATE_SUGGESTION,
        key,
        {
            TICKET_ID_FIELD: ticket_id,
            INTENT_OVERRIDE_FIELD: "" if intent_override is None else intent_override.value,
        },
    )


def _check_ticket_state(ticket: TicketForSuggestion) -> None:
    if not ticket.is_open:
        raise InvalidTicketStateError(ticket.status_name)
    if not ticket.is_assisted:
        raise InvalidTicketStateError(MANUAL_MODE_STATE)
