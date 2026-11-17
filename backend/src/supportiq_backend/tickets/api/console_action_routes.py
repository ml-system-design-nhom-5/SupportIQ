"""The console's staff actions on a ticket: a reply proposal, a reply, and an escalation.

Handlers are thin: the role check runs before the request is parsed, so another role gets
`403` whatever it sent; then each handler parses, calls one use case, and maps the result
(ARCH-14, PY-36). Each use case stores the `201` response that this module renders, so a
repeat with the same `Idempotency-Key` returns the same body.
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from supportiq_backend.accounts import AuthenticatedSession
from supportiq_backend.generated import (
    CreateEscalationRequest,
    CreateReplyProposalRequest,
    SendReplyRequest,
)
from supportiq_backend.idempotency import StoredResponse, parse_idempotency_key
from supportiq_backend.platform.web import (
    IDEMPOTENCY_KEY_HEADER,
    RequestDependency,
    parse_json_body,
    provide,
    render_json,
    stored_json_response,
)
from supportiq_backend.tickets.api.console_action_requests import (
    parse_escalation_request,
    parse_proposal_request,
    parse_reply_request,
)
from supportiq_backend.tickets.api.console_views import (
    to_escalation_view,
    to_proposal_view,
    to_reply_view,
)
from supportiq_backend.tickets.application import (
    CreateEscalation,
    CreateReplyProposal,
    SendReply,
)
from supportiq_backend.tickets.domain import (
    EscalationRecord,
    ProposalRecord,
    ReplyRecord,
    TicketId,
)


@dataclass(frozen=True, slots=True)
class ConsoleActionRoutes:
    """What the routes of the console's staff actions need from the composition root.

    Attributes:
        create_proposal: Reply proposals.
        send_reply: Replies.
        create_escalation: Escalations.
        check_origin: The `Origin` check of state-changing routes.
        current_session: The session of a request.
    """

    create_proposal: CreateReplyProposal
    send_reply: SendReply
    create_escalation: CreateEscalation
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


def render_created_proposal(record: ProposalRecord) -> StoredResponse:
    """Write the `201` response of `createReplyProposal`, the one that every repeat returns.

    Args:
        record: The proposal and its proposer's name.

    Returns:
        The status and the exact body text.
    """
    return StoredResponse(HTTPStatus.CREATED.value, render_json(to_proposal_view(record)))


def render_created_escalation(record: EscalationRecord) -> StoredResponse:
    """Write the `201` response of `createEscalation`, the one that every repeat returns.

    Args:
        record: The escalation and the name of the staff member who escalated.

    Returns:
        The status and the exact body text.
    """
    return StoredResponse(HTTPStatus.CREATED.value, render_json(to_escalation_view(record)))


def build_console_actions_router(routes: ConsoleActionRoutes) -> APIRouter:
    """Build the router of the console's staff actions on a ticket.

    Args:
        routes: The use cases and dependencies.

    Returns:
        The router.
    """
    router = APIRouter()
    _add_proposal_route(router, routes)
    _add_reply_route(router, routes)
    _add_escalation_route(router, routes)
    return router


def _add_reply_route(router: APIRouter, routes: ConsoleActionRoutes) -> None:
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


def _add_proposal_route(router: APIRouter, routes: ConsoleActionRoutes) -> None:
    current_session = Depends(routes.current_session)
    create_proposal = Depends(provide(routes.create_proposal))

    @router.post(
        "/v1/console/tickets/{ticket_id}/reply-proposals",
        status_code=HTTPStatus.CREATED,
        dependencies=[Depends(routes.check_origin)],
    )
    async def handle_create_reply_proposal(
        ticket_id: str,
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[CreateReplyProposal, create_proposal],
    ) -> Response:
        support = use_case.authorize(session.principal)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, CreateReplyProposalRequest)
        stored = await use_case.execute(
            support, TicketId(ticket_id), parse_proposal_request(body.root), key
        )
        return stored_json_response(stored.status_code, stored.body)


def _add_escalation_route(router: APIRouter, routes: ConsoleActionRoutes) -> None:
    current_session = Depends(routes.current_session)
    create_escalation = Depends(provide(routes.create_escalation))

    @router.post(
        "/v1/console/tickets/{ticket_id}/escalations",
        status_code=HTTPStatus.CREATED,
        dependencies=[Depends(routes.check_origin)],
    )
    async def handle_create_escalation(
        ticket_id: str,
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[CreateEscalation, create_escalation],
    ) -> Response:
        support = use_case.authorize(session.principal)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, CreateEscalationRequest)
        stored = await use_case.execute(
            support, TicketId(ticket_id), parse_escalation_request(body), key
        )
        return stored_json_response(stored.status_code, stored.body)
