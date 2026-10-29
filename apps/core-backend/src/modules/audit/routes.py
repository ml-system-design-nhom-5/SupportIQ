from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db import get_db_session
from src.contracts import AccessScope
from src.errors import AppError
from src.modules.auth.routes import get_current_user_scope
from src.modules.auth.service import authorize
from src.modules.audit.models import AuditEventModel

router = APIRouter(prefix="/api/v1", tags=["audit"])

@router.get("/tickets/{ticket_id}/events")
async def get_ticket_events(
    ticket_id: UUID,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    authorize(scope, {"agent", "manager"})
    stmt = select(AuditEventModel).where(AuditEventModel.ticket_id == str(ticket_id)).order_by(AuditEventModel.occurred_at)
    res = await db.execute(stmt)
    events = res.scalars().all()
    return {
        "data": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "request_id": e.request_id,
                "ticket_id": e.ticket_id,
                "run_id": e.run_id,
                "actor_id": e.actor_id,
                "details": e.details,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in events
        ]
    }
