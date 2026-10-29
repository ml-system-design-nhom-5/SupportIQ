import re
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.contracts import AccessScope, AuditEventInput
from src.errors import AppError
from src.idempotency import parse_if_match
from src.crypto import encrypt_text
from src.modules.auth.service import authorize
from src.modules.audit.service import append_event
from src.modules.tickets.service import get_ticket_for_actor
from src.modules.tickets.models import TicketModel, MessageModel
from src.modules.commerce.models import OrderModel
from src.modules.orchestration.models import PipelineRunModel, DraftModel
from src.modules.review.models import ReviewDecisionModel, ReplyModel
from src.modules.review.schemas import DecisionCreate, ReplyCreate

UNRESOLVED_TOKEN_PATTERN = re.compile(r"\{\{TOKEN_[^}]+\}\}|\[PII_[^\]]+\]")

async def record_decision(
    session: AsyncSession,
    ticket_id: UUID,
    payload: DecisionCreate,
    scope: AccessScope,
    if_match: str | None = None,
    idempotency_key: str | None = None,
) -> ReviewDecisionModel:
    authorize(scope, {"agent", "manager"})

    ticket = await get_ticket_for_actor(session, ticket_id, scope, for_update=True)
    if if_match:
        parse_if_match(if_match, ticket.version)

    now = datetime.now(timezone.utc)
    body_text = payload.body

    # Check order version if ticket has order
    order_version = 1
    if ticket.order_id:
        order = await session.get(OrderModel, ticket.order_id)
        if order and order.status != "placed":
            order_version = 2

    if payload.source == "ai":
        if not payload.draft_id:
            raise AppError(status=422, code="validation_error", title="Validation Error", detail="draft_id required for AI decisions.")
        draft = await session.get(DraftModel, str(payload.draft_id))
        if not draft:
            raise AppError(status=404, code="not_found", title="Not Found", detail="Referenced draft not found.")

        if payload.action == "approve":
            body_text = draft.draft_body
        elif payload.action == "edit":
            if not body_text:
                raise AppError(status=422, code="validation_error", title="Validation Error", detail="body required for edit action.")

        # Check for unresolved tokens
        if body_text and UNRESOLVED_TOKEN_PATTERN.search(body_text):
            raise AppError(
                status=409,
                code="state_conflict",
                title="Conflict",
                detail="Draft contains unresolved token placeholders. Cannot approve."
            )

    dec_id = uuid4()
    decision = ReviewDecisionModel(
        id=str(dec_id),
        ticket_id=str(ticket.id),
        actor_id=str(scope.actor_id),
        source=payload.source,
        action=payload.action,
        draft_id=str(payload.draft_id) if payload.draft_id else None,
        body=body_text,
        reason=payload.reason,
        order_version=order_version,
        created_at=now,
    )
    session.add(decision)

    if payload.action in ("approve", "edit"):
        ticket.current_decision_id = str(dec_id)
    else:
        # Reject clears current_decision_id
        ticket.current_decision_id = None

    ticket.version += 1
    ticket.updated_at = now

    # Audit event
    await append_event(
        session,
        AuditEventInput(
            event_type="review_decision",
            request_id=uuid4(),
            ticket_id=ticket_id,
            run_id=UUID(ticket.current_run_id) if ticket.current_run_id else None,
            actor_id=scope.actor_id,
            details={
                "decision": payload.action,
                "mode": payload.source,
                "run_id": ticket.current_run_id,
            },
        ),
    )

    await session.commit()
    await session.refresh(decision)
    return decision

async def send_reply(
    session: AsyncSession,
    ticket_id: UUID,
    payload: ReplyCreate,
    scope: AccessScope,
    if_match: str | None = None,
    idempotency_key: str | None = None,
) -> ReplyModel:
    authorize(scope, {"agent", "manager"})

    ticket = await get_ticket_for_actor(session, ticket_id, scope, for_update=True)
    if if_match:
        parse_if_match(if_match, ticket.version)

    # Invariant #1: Must match ticket.current_decision_id
    if not ticket.current_decision_id or ticket.current_decision_id != str(payload.decision_id):
        raise AppError(
            status=409,
            code="state_conflict",
            title="Conflict",
            detail="Specified decision is stale or unapproved.",
        )

    decision = await session.get(ReviewDecisionModel, str(payload.decision_id))
    if not decision or decision.action not in ("approve", "edit"):
        raise AppError(
            status=409,
            code="state_conflict",
            title="Conflict",
            detail="Cannot send reply for rejected decision.",
        )

    # Check evidence validity / order version change
    if ticket.order_id:
        order = await session.get(OrderModel, ticket.order_id)
        if order:
            order_updated = order.updated_at.replace(tzinfo=timezone.utc) if order.updated_at.tzinfo is None else order.updated_at
            dec_created = decision.created_at.replace(tzinfo=timezone.utc) if decision.created_at.tzinfo is None else decision.created_at
            if order_updated > dec_created or order.status != "placed":
                if order.status != "placed" and decision.order_version == 1:
                    raise AppError(
                        status=409,
                        code="evidence_changed",
                        title="Evidence Changed",
                        detail="Underlying order data has changed since approval. Re-review required.",
                    )

    now = datetime.now(timezone.utc)
    reply_id = uuid4()
    reply = ReplyModel(
        id=str(reply_id),
        ticket_id=str(ticket.id),
        decision_id=str(decision.id),
        actor_id=str(scope.actor_id),
        body=decision.body or "",
        created_at=now,
    )
    session.add(reply)

    # Add outbound message to ticket messages
    msg = MessageModel(
        id=str(uuid4()),
        ticket_id=str(ticket.id),
        sender_id=str(scope.actor_id),
        sender_role=scope.role,
        content_ciphertext=encrypt_text(decision.body or ""),
        created_at=now,
    )
    session.add(msg)

    # Invariant: Transition ticket to resolved and clear current_decision_id
    ticket.status = "resolved"
    ticket.current_decision_id = None
    ticket.version += 1
    ticket.updated_at = now

    await append_event(
        session,
        AuditEventInput(
            event_type="reply_delivered",
            request_id=uuid4(),
            ticket_id=ticket_id,
            actor_id=scope.actor_id,
            details={"reply_id": str(reply_id), "decision_id": str(decision.id)},
        ),
    )

    await session.commit()
    await session.refresh(reply)
    return reply
