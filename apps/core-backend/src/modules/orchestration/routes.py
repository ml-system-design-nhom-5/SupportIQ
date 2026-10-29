from uuid import UUID
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db import get_db_session
from src.contracts import AccessScope
from src.errors import AppError
from src.modules.auth.routes import get_current_user_scope
from src.modules.orchestration.models import PipelineRunModel
from src.modules.orchestration.schemas import RunCreate, RunAccepted, RunDetailResponse
from src.modules.orchestration.service import create_run

router = APIRouter(prefix="/api/v1", tags=["orchestration"])

@router.post("/tickets/{ticket_id}/runs", status_code=status.HTTP_202_ACCEPTED)
async def post_ticket_run(
    ticket_id: UUID,
    payload: RunCreate,
    if_match: str | None = Header(None, alias="If-Match"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    run_accepted = await create_run(
        session=db,
        redis=None,
        ticket_id=ticket_id,
        payload=payload,
        scope=scope,
        if_match=if_match,
        idempotency_key=idempotency_key,
    )
    return {
        "data": {
            "id": run_accepted.id,
            "ticket_id": run_accepted.ticket_id,
            "status": run_accepted.status,
            "deadline_at": run_accepted.deadline_at.isoformat(),
        }
    }

@router.get("/runs/{run_id}")
async def get_run_status(
    run_id: UUID,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(PipelineRunModel).where(PipelineRunModel.id == str(run_id))
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise AppError(status=404, code="not_found", title="Not Found", detail="Run not found.")

    if scope.role == "customer" and run.customer_id != str(scope.actor_id):
        raise AppError(status=404, code="not_found", title="Not Found", detail="Run not found.")

    return {
        "data": {
            "id": run.id,
            "ticket_id": run.ticket_id,
            "customer_id": run.customer_id,
            "status": run.status,
            "stage": run.stage,
            "reason_codes": run.reason_codes,
            "deadline_at": run.deadline_at.isoformat(),
            "cost_status": run.cost_status,
            "cost_micro": run.cost_micro,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
        }
    }
