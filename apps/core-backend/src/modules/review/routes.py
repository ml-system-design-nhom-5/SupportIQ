from uuid import UUID
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db import get_db_session
from src.contracts import AccessScope
from src.errors import AppError
from src.modules.auth.routes import get_current_user_scope
from src.modules.auth.service import authorize
from src.modules.review.models import ReviewDecisionModel
from src.modules.review.schemas import DecisionCreate, ReplyCreate
from src.modules.review.service import record_decision, send_reply

router = APIRouter(prefix="/api/v1/tickets/{ticket_id}", tags=["review"])

@router.post("/decisions", status_code=status.HTTP_201_CREATED)
async def post_decision(
    ticket_id: UUID,
    payload: DecisionCreate,
    if_match: str | None = Header(None, alias="If-Match"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    dec = await record_decision(
        session=db,
        ticket_id=ticket_id,
        payload=payload,
        scope=scope,
        if_match=if_match,
        idempotency_key=idempotency_key,
    )
    return {
        "data": {
            "id": dec.id,
            "ticket_id": dec.ticket_id,
            "actor_id": dec.actor_id,
            "source": dec.source,
            "action": dec.action,
            "draft_id": dec.draft_id,
            "body": dec.body,
            "reason": dec.reason,
            "order_version": dec.order_version,
            "created_at": dec.created_at.isoformat(),
        }
    }

@router.get("/decisions")
async def get_decisions(
    ticket_id: UUID,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    authorize(scope, {"agent", "manager"})
    stmt = select(ReviewDecisionModel).where(ReviewDecisionModel.ticket_id == str(ticket_id)).order_by(ReviewDecisionModel.created_at)
    res = await db.execute(stmt)
    decisions = res.scalars().all()
    return {
        "data": [
            {
                "id": d.id,
                "ticket_id": d.ticket_id,
                "actor_id": d.actor_id,
                "source": d.source,
                "action": d.action,
                "draft_id": d.draft_id,
                "body": d.body,
                "reason": d.reason,
                "order_version": d.order_version,
                "created_at": d.created_at.isoformat(),
            }
            for d in decisions
        ]
    }

@router.post("/replies", status_code=status.HTTP_201_CREATED)
async def post_reply(
    ticket_id: UUID,
    payload: ReplyCreate,
    if_match: str | None = Header(None, alias="If-Match"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    reply = await send_reply(
        session=db,
        ticket_id=ticket_id,
        payload=payload,
        scope=scope,
        if_match=if_match,
        idempotency_key=idempotency_key,
    )
    return {
        "data": {
            "id": reply.id,
            "ticket_id": reply.ticket_id,
            "decision_id": reply.decision_id,
            "actor_id": reply.actor_id,
            "body": reply.body,
            "created_at": reply.created_at.isoformat(),
        }
    }
