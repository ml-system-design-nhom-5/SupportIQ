from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from src.contracts import AuditEventInput
from src.modules.audit.service import append_event

async def record_feedback(
    session: AsyncSession,
    ticket_id: UUID,
    actor_id: UUID,
    decision_id: UUID,
    action: str,
    reason: str | None = None,
) -> None:
    pass
