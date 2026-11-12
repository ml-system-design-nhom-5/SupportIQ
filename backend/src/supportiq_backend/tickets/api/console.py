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

from supportiq_backend.accounts import AuthenticatedSession, OperationId
from supportiq_backend.generated import (
    CreateSuggestionRequest,
    Cursor,
    SendReplyRequest,
)
from supportiq_backend.generated import (
    TicketSummaryPage as ContractTicketSummaryPage,
)
from supportiq_backend.idempotency import StoredResponse, parse_idempotency_key
from supportiq_backend.platform import InvalidCursorError, InvalidRequestError
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
from supportiq_backend.suggestions import (
    CreateSuggestion,
    IntentLabel,
    Suggestion,
    SuggestionTicketId,
)
from supportiq_backend.tickets.api.console_views import (
    to_pending_suggestion_view,
    to_reply_request,
    to_reply_view,
    to_ticket_summary,
    to_workspace,
)
from supportiq_backend.tickets.application import (
    GetConsoleTicket,
    ListConsoleTickets,
    RecordTicketView,
    SendReply,
)
from supportiq_backend.tickets.domain import (
    ConsoleTicketPosition,
    ReplyRecord,
    TicketId,
    TicketStatus,
    TicketSummaryPage,
)

LIST_OPERATION = OperationId.LIST_CONSOLE_TICKETS.value
CURSOR_STATUS_FIELD = "status"
CURSOR_MOMENT_FIELD = "moment"
CURSOR_TICKET_FIELD = "ticket_id"


class InvalidStatusFilterError(InvalidRequestError):
    """The `status` parameter of `listConsoleTickets` is missing or unknown (422)."""

    def __init__(self) -> None:
        """Build the error with the detail of its contract example."""
        super().__init__(
            "The parameter status must be open, awaiting_approval, escalated, or closed."
        )


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
    """

    list_tickets: ListConsoleTickets
    get_ticket: GetConsoleTicket
    record_view: RecordTicketView
    create_suggestion: CreateSuggestion
    send_reply: SendReply
    check_origin: RequestDependency[None]
    current_session: RequestDependency[AuthenticatedSession]


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


def parse_status_filter(raw: str | None) -> TicketStatus:
    """Read the required `status` parameter of `listConsoleTickets`.

    Args:
        raw: The parameter as sent, or None when absent.

    Returns:
        The queue.

    Raises:
        InvalidStatusFilterError: The parameter is missing or unknown.
    """
    try:
        return TicketStatus(raw)
    except ValueError as error:
        raise InvalidStatusFilterError from error


def parse_console_cursor(raw: str | None, status: TicketStatus) -> ConsoleTicketPosition | None:
    """Read the cursor of `listConsoleTickets`: the last ticket of the previous page.

    Args:
        raw: The `cursor` query parameter, or None when absent.
        status: The queue of this request; a cursor of another queue is refused.

    Returns:
        The position, or None for the first page.

    Raises:
        InvalidCursorError: The cursor is malformed, from another operation, or another queue.
    """
    fields = decode_cursor(
        raw,
        LIST_OPERATION,
        frozenset({CURSOR_STATUS_FIELD, CURSOR_MOMENT_FIELD, CURSOR_TICKET_FIELD}),
    )
    if fields is None:
        return None
    if fields.text(CURSOR_STATUS_FIELD) != status.value:
        raise InvalidCursorError
    return ConsoleTicketPosition(
        status, fields.timestamp(CURSOR_MOMENT_FIELD), TicketId(fields.text(CURSOR_TICKET_FIELD))
    )


def to_summary_page(page: TicketSummaryPage) -> ContractTicketSummaryPage:
    """Map a page of a queue to the contract.

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
                    CURSOR_STATUS_FIELD: position.status.value,
                    CURSOR_MOMENT_FIELD: format_timestamp(position.moment),
                    CURSOR_TICKET_FIELD: position.ticket_id,
                },
            )
        )
    return ContractTicketSummaryPage(
        items=[to_ticket_summary(summary) for summary in page.items], next_cursor=next_cursor
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
    _add_write_routes(router, routes)
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
        use_case.authorize(session.principal)
        queue = parse_status_filter(status)
        page = await use_case.execute(
            session.principal, queue, parse_console_cursor(cursor, queue), parse_limit(limit)
        )
        return json_response(to_summary_page(page))

    @router.get("/v1/console/tickets/{ticket_id}", status_code=HTTPStatus.OK)
    async def handle_get_console_ticket(
        ticket_id: str,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetConsoleTicket, get_ticket],
    ) -> Response:
        workspace = await use_case.execute(session.principal, TicketId(ticket_id))
        return json_response(to_workspace(workspace))


def _add_write_routes(router: APIRouter, routes: ConsoleTicketRoutes) -> None:
    check_origin = Depends(routes.check_origin)
    current_session = Depends(routes.current_session)
    record_view = Depends(provide(routes.record_view))
    create_suggestion = Depends(provide(routes.create_suggestion))
    send_reply = Depends(provide(routes.send_reply))

    @router.post(
        "/v1/console/tickets/{ticket_id}/views",
        status_code=HTTPStatus.NO_CONTENT,
        dependencies=[check_origin],
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

    @router.post(
        "/v1/console/tickets/{ticket_id}/suggestions",
        status_code=HTTPStatus.ACCEPTED,
        dependencies=[check_origin],
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

    @router.post(
        "/v1/console/tickets/{ticket_id}/replies",
        status_code=HTTPStatus.CREATED,
        dependencies=[check_origin],
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
            support, TicketId(ticket_id), to_reply_request(body.root), key
        )
        return stored_json_response(stored.status_code, stored.body)
