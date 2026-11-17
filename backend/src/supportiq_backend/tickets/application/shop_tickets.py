"""The shop's ticket use cases: writing to support and reading one's own tickets (ADR-0013)."""

from collections.abc import Callable
from dataclasses import dataclass

from supportiq_backend.accounts import (
    Authorizer,
    CustomerPrincipal,
    Principal,
)
from supportiq_backend.commerce import CommerceGateway, OrderId, OrderNotFoundError
from supportiq_backend.idempotency import (
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyStore,
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
    SpanName,
    StepTracer,
    TransactionRunner,
)
from supportiq_backend.suggestions import (
    StartedSuggestion,
    SuggestionStart,
    SuggestionStarter,
    SuggestionStore,
    SuggestionTicketId,
    SuggestionTickets,
    SuggestionTrigger,
)
from supportiq_backend.tickets.domain import (
    HandlingMode,
    NewShopTicket,
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketNotFoundError,
    TicketPage,
    TicketPosition,
    TicketStore,
)


@dataclass(frozen=True, slots=True)
class ShopTicketStores:
    """The stores of the ticket use cases, all in one transaction.

    Attributes:
        tickets: The tickets of the shop.
        orders: Tells whose orders are whose. It stays read-only.
        idempotency: The idempotency records.
        suggestions: The suggestions, for the first one of an assisted ticket.
        links: The ticket rows that suggestions links.
    """

    tickets: TicketStore
    orders: CommerceGateway
    idempotency: IdempotencyStore
    suggestions: SuggestionStore
    links: SuggestionTickets


@dataclass(frozen=True, slots=True)
class CreateShopTicketPorts:
    """The ports of ticket creation besides its stores.

    Attributes:
        guard: The idempotency guard.
        authorizer: The role checks.
        clock: The clock.
        ids: Generates the IDs of customer messages.
        events: Where events are recorded.
        steps: Runs the creation in its span (LOG-20).
        starter: Starts the first suggestion of an assisted ticket.
    """

    guard: IdempotencyGuard
    authorizer: Authorizer
    clock: Clock
    ids: IdGenerator
    events: EventRecorder
    steps: StepTracer
    starter: SuggestionStarter


class CreateShopTicket:
    """Create a ticket from a customer's message about their order (`createShopTicket`).

    The design's diagram, step by step: the idempotency record first, then the order check,
    and the ticket, its message, and the stored response in one transaction. In `assisted`
    mode the same transaction starts the first suggestion and queues its job. The customer
    never waits for AI: nothing here calls `ai-service`.
    """

    def __init__(
        self,
        transactions: TransactionRunner[ShopTicketStores],
        ports: CreateShopTicketPorts,
        default_handling_mode: HandlingMode,
        render_response: Callable[[ShopTicket], StoredResponse],
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of a creation.
            ports: The ports besides the stores.
            default_handling_mode: The handling mode of new tickets.
            render_response: Writes the response of a creation, the one that every repeat of
                the request returns. The interface layer provides it.
        """
        self._transactions = transactions
        self._ports = ports
        self._default_handling_mode = default_handling_mode
        self._render_response = render_response

    def authorize(self, principal: Principal) -> CustomerPrincipal:
        """Allow only a customer, before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a customer.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
        """
        return self._ports.authorizer.require_customer(principal, OperationId.CREATE_SHOP_TICKET)

    async def execute(
        self, customer: CustomerPrincipal, ticket: NewShopTicket, key: IdempotencyKey
    ) -> StoredResponse:
        """Create the ticket, or return the response of the first request with this key.

        Args:
            customer: The caller.
            ticket: The order and the message.
            key: The `Idempotency-Key`.

        Returns:
            The response of the creation.

        Raises:
            OrderNotFoundError: The order is unknown or another customer's. Nothing is created.
            IdempotencyKeyReusedError: The key was used with a different request.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        with self._ports.steps.step(SpanName.CREATE_TICKET):
            return await self._create(customer, ticket, key)

    async def _create(
        self, customer: CustomerPrincipal, ticket: NewShopTicket, key: IdempotencyKey
    ) -> StoredResponse:
        request = build_idempotent_request(
            RequesterId(customer.account_id),
            OperationId.CREATE_SHOP_TICKET,
            key,
            {"order_id": ticket.order_id, "message": ticket.message},
        )
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            claim = await self._ports.guard.claim(stores.idempotency, request)
            if isinstance(claim, RepeatedRequest):
                return claim.response
            if not await stores.orders.is_order_of_customer(customer.customer_id, ticket.order_id):
                raise OrderNotFoundError
            created_at = self._ports.clock.now()
            ticket_id = await stores.tickets.insert_shop_ticket(
                ShopTicketRecord(
                    customer_id=customer.customer_id,
                    ticket=ticket,
                    message_id=self._ports.ids.generate(),
                    handling_mode=self._default_handling_mode,
                    created_at=created_at,
                )
            )
            self._ports.steps.record_ticket(ticket_id)
            started = await self._start_first_suggestion(stores, ticket_id)
            response = self._render_response(
                ShopTicket(ticket_id, ticket.order_id, ticket.message, created_at)
            )
            await stores.idempotency.save_response(request, response)
            await transaction.commit()
        self._ports.events.record(EventName.TICKET_CREATED, ticket_id=ticket_id)
        if started is not None:
            self._ports.starter.announce(started)
        return response

    async def _start_first_suggestion(
        self, stores: ShopTicketStores, ticket_id: TicketId
    ) -> StartedSuggestion | None:
        # A ticket in manual mode never gets a suggestion (backend ticket workflow design).
        if self._default_handling_mode is HandlingMode.MANUAL:
            return None
        return await self._ports.starter.start(
            stores.suggestions,
            stores.links,
            SuggestionStart(
                SuggestionTicketId(ticket_id),
                SuggestionTrigger.TICKET_CREATED,
                intent_override=None,
                requested_by=None,
            ),
        )


class ListShopTickets:
    """Return one page of the caller's own tickets (`listShopTickets`, SEC-17)."""

    def __init__(
        self, transactions: TransactionRunner[ShopTicketStores], authorizer: Authorizer
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the read.
            authorizer: The role checks.
        """
        self._transactions = transactions
        self._authorizer = authorizer

    def authorize(self, principal: Principal) -> CustomerPrincipal:
        """Allow only a customer, before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a customer.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
        """
        return self._authorizer.require_customer(principal, OperationId.LIST_SHOP_TICKETS)

    async def execute(
        self,
        customer: CustomerPrincipal,
        order_id: OrderId | None,
        after: TicketPosition | None,
        limit: int,
    ) -> TicketPage:
        """Load one page of the customer's tickets.

        Args:
            customer: The caller, whose `customer_id` filters every page.
            order_id: Only the tickets about this order, or None for every ticket.
            after: The last ticket of the previous page, or None for the first page.
            limit: The maximum number of tickets.

        Returns:
            The page.

        Raises:
            OrderNotFoundError: The order is unknown or another customer's.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            if order_id is not None and not await stores.orders.is_order_of_customer(
                customer.customer_id, order_id
            ):
                raise OrderNotFoundError
            tickets = await stores.tickets.load_shop_tickets(
                customer.customer_id, order_id=order_id, after=after, limit=limit + 1
            )
        items = tickets[:limit]
        last = items[-1] if len(tickets) > limit else None
        next_position = None if last is None else TicketPosition(last.created_at, last.ticket_id)
        return TicketPage(items, next_position)


class GetShopTicket:
    """Return one of the caller's tickets (`getShopTicket`, SEC-17)."""

    def __init__(
        self, transactions: TransactionRunner[ShopTicketStores], authorizer: Authorizer
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the read.
            authorizer: The role checks.
        """
        self._transactions = transactions
        self._authorizer = authorizer

    async def execute(self, principal: Principal, ticket_id: TicketId) -> ShopTicket:
        """Load one ticket of the caller.

        Args:
            principal: The caller.
            ticket_id: The identifier.

        Returns:
            The ticket.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
            TicketNotFoundError: The ticket is unknown, imported, or another customer's.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        customer = self._authorizer.require_customer(principal, OperationId.GET_SHOP_TICKET)
        async with self._transactions.begin() as transaction:
            ticket = await transaction.stores.tickets.load_shop_ticket(
                customer.customer_id, ticket_id
            )
        if ticket is None:
            raise TicketNotFoundError
        return ticket
