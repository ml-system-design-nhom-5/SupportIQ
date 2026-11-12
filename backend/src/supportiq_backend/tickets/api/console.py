"""The console's ticket operations: list, workspace, view, suggestion, and reply.

Handlers are thin: the role check runs before the request is parsed, so another role gets
`403` whatever it sent; then each handler parses, calls one use case, and maps the result
(ARCH-14, PY-36).
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import MISSING

from supportiq_backend.accounts import AuthenticatedSession
from supportiq_backend.generated import CreateSuggestionRequest, SendReplyRequest
from supportiq_backend.idempotency import StoredResponse, parse_idempotency_key
from supportiq_backend.platform.web import (
    IDEMPOTENCY_KEY_HEADER,
    RequestDependency,
    json_response,
    parse_json_body,
    parse_limit,
    provide,
    render_json,
    stored_json_response,
)
from supportiq_backend.suggestions import (
    CreateSuggestion,
    IntentLabel,
    Suggestion,
    SuggestionTicketId,
)
from supportiq_backend.tickets.api.console_queues import (
    parse_console_cursor,
    parse_status_filter,
    to_summary_page,
)
from supportiq_backend.tickets.api.console_reply_requests import parse_reply_request
from supportiq_backend.tickets.api.console_suggestion_views import to_pending_suggestion_view
from supportiq_backend.tickets.api.console_views import to_reply_view, to_workspace
from supportiq_backend.tickets.api.order_views import OrderViewMappers
from supportiq_backend.tickets.application import (
    GetConsoleTicket,
    ListConsoleTickets,
    RecordTicketView,
    SendReply,
)
from supportiq_backend.tickets.domain import ReplyRecord, TicketId


@dataclass(frozen=True, slots=True)
class ConsoleTicketRoutes:
    """What the console's ticket routes need from the composition root.

    Attributes:
        list_tickets: The queues.
        get_ticket: The workspace.
        record_view: The views.
        create_suggestion: Intent corrections and retries.
        send_reply: Replies.
        check_origin: The `Origin` check of state-changing routes.
        current_session: The session of a request.
        order_views: The order mappings of commerce that the workspace reuses.
    """

    list_tickets: ListConsoleTickets
    get_ticket: GetConsoleTicket
    record_view: RecordTicketView
    create_suggestion: CreateSuggestion
    send_reply: SendReply
    check_origin: RequestDependency[None]
    current_session: RequestDependency[AuthenticatedSession]
    order_views: OrderViewMappers


def render_sent_reply(record: ReplyRecord) -> StoredResponse:
    """Write the `201` response of `sendReply`, the one that every repeat returns.

    Args:
        record: The reply and its sender's name.

    Returns:
        The status and the exact body text.
    """
    return StoredResponse(HTTPStatus.CREATED.value, render_json(to_reply_view(record)))


def render_created_suggestion(suggestion: Suggestion) -> StoredResponse:
    """Write the `202` response of `createSuggestion`, the one that every repeat returns.

    Args:
        suggestion: The new, pending suggestion.

    Returns:
        The status and the exact body text.
    """
    return StoredResponse(
        HTTPStatus.ACCEPTED.value, render_json(to_pending_suggestion_view(suggestion))
    )


def build_console_tickets_router(routes: ConsoleTicketRoutes) -> APIRouter:
    """Build the router of the console's ticket operations.

    Args:
        routes: The use cases and dependencies.

    Returns:
        The router.
    """
    router = APIRouter()
    _add_read_routes(router, routes)
    _add_view_route(router, routes)
    _add_suggestion_route(router, routes)
    _add_reply_route(router, routes)
    return router


def _add_read_routes(router: APIRouter, routes: ConsoleTicketRoutes) -> None:
    current_session = Depends(routes.current_session)
    list_tickets = Depends(provide(routes.list_tickets))
    get_ticket = Depends(provide(routes.get_ticket))

    @router.get("/v1/console/tickets", status_code=HTTPStatus.OK)
    async def handle_list_console_tickets(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ListConsoleTickets, list_tickets],
        status: Annotated[str | None, Query()] = None,
        limit: Annotated[str | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
    ) -> Response:
        support = use_case.authorize(session.principal)
        queue = parse_status_filter(status)
        page = await use_case.execute(
            support, queue, parse_console_cursor(cursor, queue), parse_limit(limit)
        )
        return json_response(to_summary_page(page))

    @router.get("/v1/console/tickets/{ticket_id}", status_code=HTTPStatus.OK)
    async def handle_get_console_ticket(
        ticket_id: str,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetConsoleTicket, get_ticket],
    ) -> Response:
        workspace = await use_case.execute(session.principal, TicketId(ticket_id))
        return json_response(to_workspace(workspace, routes.order_views))


def _add_view_route(router: APIRouter, routes: ConsoleTicketRoutes) -> None:
    current_session = Depends(routes.current_session)
    record_view = Depends(provide(routes.record_view))

    @router.post(
        "/v1/console/tickets/{ticket_id}/views",
        status_code=HTTPStatus.NO_CONTENT,
        dependencies=[Depends(routes.check_origin)],
    )
    async def handle_record_ticket_view(
        ticket_id: str,
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[RecordTicketView, record_view],
    ) -> Response:
        support = use_case.authorize(session.principal)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        await use_case.execute(support, TicketId(ticket_id), key)
        return Response(status_code=HTTPStatus.NO_CONTENT)


def _add_suggestion_route(router: APIRouter, routes: ConsoleTicketRoutes) -> None:
    current_session = Depends(routes.current_session)
    create_suggestion = Depends(provide(routes.create_suggestion))

    @router.post(
        "/v1/console/tickets/{ticket_id}/suggestions",
        status_code=HTTPStatus.ACCEPTED,
        dependencies=[Depends(routes.check_origin)],
    )
    async def handle_create_suggestion(
        ticket_id: str,
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[CreateSuggestion, create_suggestion],
    ) -> Response:
        support = use_case.authorize(session.principal)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, CreateSuggestionRequest)
        override = (
            None if body.intent_override is MISSING else IntentLabel(body.intent_override.value)
        )
        stored = await use_case.execute(support, SuggestionTicketId(ticket_id), override, key)
        return stored_json_response(stored.status_code, stored.body)


def _add_reply_route(router: APIRouter, routes: ConsoleTicketRoutes) -> None:
    current_session = Depends(routes.current_session)
    send_reply = Depends(provide(routes.send_reply))

    @router.post(
        "/v1/console/tickets/{ticket_id}/replies",
        status_code=HTTPStatus.CREATED,
        dependencies=[Depends(routes.check_origin)],
    )
    async def handle_send_reply(
        ticket_id: str,
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[SendReply, send_reply],
    ) -> Response:
        support = use_case.authorize(session.principal)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, SendReplyRequest)
        stored = await use_case.execute(
            support, TicketId(ticket_id), parse_reply_request(body.root), key
        )
        return stored_json_response(stored.status_code, stored.body)
