"""The shop's ticket operations: `listShopTickets`, `createShopTicket`, `getShopTicket`."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import MISSING

from supportiq_backend.accounts import AuthenticatedSession, OperationId
from supportiq_backend.commerce import OrderId
from supportiq_backend.generated import (
    CreateShopTicketRequest,
    Cursor,
    MessageText,
    ShopTicketPage,
    ShopTicketStatus,
    ShopTicketView,
)
from supportiq_backend.idempotency import StoredResponse, parse_idempotency_key
from supportiq_backend.platform import InvalidParameterError
from supportiq_backend.platform.web import (
    IDEMPOTENCY_KEY_HEADER,
    RequestDependency,
    decode_cursor,
    encode_cursor,
    format_timestamp,
    json_response,
    parse_json_body,
    parse_limit,
    provide,
    render_json,
    stored_json_response,
)
from supportiq_backend.tickets.application import (
    CreateShopTicket,
    GetShopTicket,
    ListShopTickets,
)
from supportiq_backend.tickets.domain import (
    ShopTicket,
    TicketId,
    TicketPage,
    TicketPosition,
    build_new_shop_ticket,
)

LIST_OPERATION = OperationId.LIST_SHOP_TICKETS.value
CURSOR_CREATED_AT_FIELD = "created_at"
CURSOR_TICKET_FIELD = "ticket_id"
ORDER_FILTER_NAME = "order_id"


@dataclass(frozen=True, slots=True)
class ShopTicketRoutes:
    """What the ticket routes of the shop need from the composition root.

    Attributes:
        list_tickets: The caller's tickets.
        create_ticket: Ticket creation.
        get_ticket: One ticket of the caller.
        check_origin: The `Origin` check of state-changing routes.
        current_session: The session of a request.
    """

    list_tickets: ListShopTickets
    create_ticket: CreateShopTicket
    get_ticket: GetShopTicket
    check_origin: RequestDependency[None]
    current_session: RequestDependency[AuthenticatedSession]


def to_shop_ticket_view(ticket: ShopTicket) -> ShopTicketView:
    """Map a ticket to the contract, without any field that could hold AI output.

    Args:
        ticket: The ticket.

    Returns:
        The contract model. Every ticket is `received`, because no operation sends a reply
        until the ticket workflow adds them.
    """
    return ShopTicketView(
        ticket_id=ticket.ticket_id,
        order_id=ticket.order_id,
        message=MessageText(ticket.message),
        created_at=format_timestamp(ticket.created_at),
        customer_status=ShopTicketStatus.received,
    )


def render_created_ticket(ticket: ShopTicket) -> StoredResponse:
    """Write the `201` response of a creation, the one that every repeat returns.

    Args:
        ticket: The new ticket.

    Returns:
        The status and the exact body text.
    """
    return StoredResponse(HTTPStatus.CREATED.value, render_json(to_shop_ticket_view(ticket)))


def to_ticket_page(page: TicketPage) -> ShopTicketPage:
    """Map a page of tickets to the contract.

    Args:
        page: The page.

    Returns:
        The contract model; `next_cursor` is absent on the last page.
    """
    position = page.next_position
    next_cursor: Cursor | MISSING = MISSING
    if position is not None:
        next_cursor = Cursor(
            encode_cursor(
                LIST_OPERATION,
                {
                    CURSOR_CREATED_AT_FIELD: format_timestamp(position.created_at),
                    CURSOR_TICKET_FIELD: position.ticket_id,
                },
            )
        )
    return ShopTicketPage(
        items=[to_shop_ticket_view(ticket) for ticket in page.items], next_cursor=next_cursor
    )


def parse_ticket_cursor(raw: str | None) -> TicketPosition | None:
    """Read the cursor of `listShopTickets`: the last ticket of the previous page.

    The `order_id` filter is not in the cursor, because an order ID is Confidential.

    Args:
        raw: The `cursor` query parameter, or None when absent.

    Returns:
        The position, or None for the first page.

    Raises:
        InvalidCursorError: The cursor is malformed or from another operation.
    """
    fields = decode_cursor(
        raw, LIST_OPERATION, frozenset({CURSOR_CREATED_AT_FIELD, CURSOR_TICKET_FIELD})
    )
    if fields is None:
        return None
    return TicketPosition(
        fields.timestamp(CURSOR_CREATED_AT_FIELD), TicketId(fields.text(CURSOR_TICKET_FIELD))
    )


def parse_order_filter(raw: str | None) -> OrderId | None:
    """Read the `order_id` query parameter of `listShopTickets`.

    Args:
        raw: The parameter as sent, or None when absent.

    Returns:
        The order, or None for every ticket of the caller.

    Raises:
        InvalidParameterError: The parameter is empty, which the contract does not allow.
    """
    if raw is None:
        return None
    if not raw:
        raise InvalidParameterError(ORDER_FILTER_NAME)
    return OrderId(raw)


def build_shop_tickets_router(routes: ShopTicketRoutes) -> APIRouter:
    """Build the router of the shop's ticket operations.

    The role check runs before the request is parsed, so a caller with another role gets
    `403` whatever it sent (contract, Authentication and roles).

    Args:
        routes: The use cases and dependencies.

    Returns:
        The router.
    """
    router = APIRouter()
    check_origin = Depends(routes.check_origin)
    current_session = Depends(routes.current_session)
    list_tickets = Depends(provide(routes.list_tickets))
    create_ticket = Depends(provide(routes.create_ticket))
    get_ticket = Depends(provide(routes.get_ticket))

    @router.get("/v1/shop/tickets", status_code=HTTPStatus.OK)
    async def handle_list_shop_tickets(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ListShopTickets, list_tickets],
        limit: Annotated[str | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        order_id: Annotated[str | None, Query()] = None,
    ) -> Response:
        customer = use_case.authorize(session.principal)
        page = await use_case.execute(
            customer, parse_order_filter(order_id), parse_ticket_cursor(cursor), parse_limit(limit)
        )
        return json_response(to_ticket_page(page))

    @router.post("/v1/shop/tickets", status_code=HTTPStatus.CREATED, dependencies=[check_origin])
    async def handle_create_shop_ticket(
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[CreateShopTicket, create_ticket],
    ) -> Response:
        customer = use_case.authorize(session.principal)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, CreateShopTicketRequest)
        ticket = build_new_shop_ticket(body.order_id, body.message.root)
        stored = await use_case.execute(customer, ticket, key)
        return stored_json_response(stored.status_code, stored.body)

    @router.get("/v1/shop/tickets/{ticket_id}", status_code=HTTPStatus.OK)
    async def handle_get_shop_ticket(
        ticket_id: str,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetShopTicket, get_ticket],
    ) -> Response:
        ticket = await use_case.execute(session.principal, TicketId(ticket_id))
        return json_response(to_shop_ticket_view(ticket))

    return router
