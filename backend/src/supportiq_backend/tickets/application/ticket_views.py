"""Record a view of a ticket, which starts its handling clock (`recordTicketView`).

The first view of an assisted ticket checks the KB version that `ai-service` serves, and a
later view of a ticket whose AI could not run retries it (backend ticket workflow design,
Views and the triggers of new suggestions).
"""

from http import HTTPStatus

from supportiq_backend.accounts import Principal, SupportPrincipal
from supportiq_backend.idempotency import (
    NO_CONTENT_BODY,
    IdempotencyKey,
    RepeatedRequest,
    RequesterId,
    StoredResponse,
    build_idempotent_request,
)
from supportiq_backend.platform import EventName, OperationId, TransactionRunner
from supportiq_backend.suggestions import (
    AiServiceOperation,
    AiServiceUnavailableError,
    StartedSuggestion,
    Suggestion,
    SuggestionStart,
    SuggestionTicketId,
    SuggestionTrigger,
    choose_view_trigger,
    record_ai_service_failure,
)
from supportiq_backend.tickets.application.console_ports import (
    ConsolePorts,
    ConsoleStores,
    load_current_suggestion,
)
from supportiq_backend.tickets.domain import (
    ConsoleTicket,
    HandlingMode,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
)

# The stored response of a view: `204` without a body (contract `recordTicketView`).
VIEW_RECORDED = StoredResponse(HTTPStatus.NO_CONTENT.value, NO_CONTENT_BODY)
TICKET_ID_FIELD = "ticket_id"


class RecordTicketView:
    """Record that a person opened a ticket (`recordTicketView`)."""

    def __init__(self, transactions: TransactionRunner[ConsoleStores], ports: ConsolePorts) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the view.
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
        return self._ports.authorizer.require_support(principal, OperationId.RECORD_TICKET_VIEW)

    async def execute(
        self, support: SupportPrincipal, ticket_id: TicketId, key: IdempotencyKey
    ) -> StoredResponse:
        """Record the view; the first one starts the handling clock (NFR-11).

        The KB version of a first view is read from ai-service before any transaction, so no
        transaction waits for ai-service. When ai-service does not answer in time, the view is
        still recorded and no `kb_version_changed` suggestion starts.

        Args:
            support: The caller.
            ticket_id: The ticket.
            key: The `Idempotency-Key`.

        Returns:
            The `204` of the view, or the response of the first request with this key.

        Raises:
            TicketNotFoundError: The ticket is unknown.
            IdempotencyKeyReusedError: The key was used with a different request.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        loaded_kb_version = await self._read_kb_version_of_first_view(ticket_id)
        request = build_idempotent_request(
            RequesterId(support.account_id),
            OperationId.RECORD_TICKET_VIEW,
            key,
            {TICKET_ID_FIELD: ticket_id},
        )
        started: StartedSuggestion | None = None
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            ticket = await stores.tickets.lock_console_ticket(ticket_id)
            if ticket is None:
                raise TicketNotFoundError
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            is_first_view = ticket.handling_started_at is None
            if is_first_view:
                await stores.tickets.start_handling(ticket_id, self._ports.clock.now())
            started = await self._start_suggestion(
                stores,
                ticket,
                support,
                await self._choose_trigger(stores, ticket, is_first_view, loaded_kb_version),
            )
            await stores.idempotency.save_response(request, VIEW_RECORDED)
            await transaction.commit()
        if started is not None:
            self._ports.starter.announce(started)
        self._ports.events.record(EventName.TICKET_VIEWED, ticket_id=ticket_id)
        return VIEW_RECORDED

    async def _read_kb_version_of_first_view(self, ticket_id: TicketId) -> str | None:
        async with self._transactions.begin() as transaction:
            ticket = await transaction.stores.tickets.load_console_ticket(ticket_id)
        # Only a first view of a ticket with a suggestion can need a new one for its KB.
        needs_kb_check = (
            ticket is not None
            and _is_ai_handled(ticket)
            and ticket.handling_started_at is None
            and ticket.current_suggestion_id is not None
        )
        if not needs_kb_check:
            return None
        try:
            versions = await self._ports.ai_service.fetch_asset_versions()
        except AiServiceUnavailableError as error:
            # The view is recorded without a KB check (backend ticket workflow design); the
            # failure is logged once, at `error` when it is a contract violation.
            record_ai_service_failure(
                self._ports.events,
                AiServiceOperation.GET_ASSET_VERSIONS,
                error,
                ticket_id=ticket_id,
            )
            return None
        return versions.kb_version

    async def _choose_trigger(
        self,
        stores: ConsoleStores,
        ticket: ConsoleTicket,
        is_first_view: bool,
        loaded_kb_version: str | None,
    ) -> tuple[Suggestion, SuggestionTrigger] | None:
        if not _is_ai_handled(ticket):
            return None
        suggestion = await load_current_suggestion(stores.suggestions, ticket)
        if suggestion is None:
            return None
        trigger = choose_view_trigger(
            suggestion, is_first_view=is_first_view, loaded_kb_version=loaded_kb_version
        )
        return None if trigger is None else (suggestion, trigger)

    async def _start_suggestion(
        self,
        stores: ConsoleStores,
        ticket: ConsoleTicket,
        support: SupportPrincipal,
        chosen: tuple[Suggestion, SuggestionTrigger] | None,
    ) -> StartedSuggestion | None:
        if chosen is None:
            return None
        suggestion, trigger = chosen
        # A new suggestion repeats the input of the current one, an intent that staff chose
        # included (backend ticket workflow design, Calls).
        return await self._ports.starter.start(
            stores.suggestions,
            stores.links,
            SuggestionStart(
                SuggestionTicketId(ticket.ticket_id),
                trigger,
                suggestion.intent_override,
                support.account_id,
            ),
        )


def _is_ai_handled(ticket: ConsoleTicket) -> bool:
    return ticket.status is TicketStatus.OPEN and ticket.handling_mode is HandlingMode.ASSISTED
