from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.contracts import AccessScope
from src.errors import AppError
from src.idempotency import parse_if_match
from src.modules.tickets.service import get_ticket_for_actor
from src.modules.orchestration.models import PipelineRunModel, JobModel
from src.modules.orchestration.schemas import RunCreate, RunAccepted

TOTAL_DEADLINE_SECONDS = 12

async def supersede_active_runs(session: AsyncSession, ticket_id: UUID, reason: str = "new_run_created") -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        update(PipelineRunModel)
        .where(
            PipelineRunModel.ticket_id == str(ticket_id),
            PipelineRunModel.status.in_(["queued", "running"]),
        )
        .values(status="superseded", updated_at=now)
    )
    await session.execute(stmt)

    job_stmt = (
        update(JobModel)
        .where(
            JobModel.run_id.in_(
                select(PipelineRunModel.id).where(PipelineRunModel.ticket_id == str(ticket_id))
            ),
            JobModel.status.in_(["queued", "running"]),
        )
        .values(status="cancelled", updated_at=now)
    )
    await session.execute(job_stmt)

async def create_run(
    session: AsyncSession,
    redis: Any,
    ticket_id: UUID,
    payload: RunCreate,
    scope: AccessScope,
    if_match: str | None,
    idempotency_key: str | None = None,
) -> RunAccepted:
    ticket = await get_ticket_for_actor(session, ticket_id, scope, for_update=True)
    if if_match:
        parse_if_match(if_match, ticket.version)

    now = datetime.now(timezone.utc)
    deadline_at = now + timedelta(seconds=TOTAL_DEADLINE_SECONDS)

    # Supersede older active runs
    await supersede_active_runs(session, ticket_id, reason="superseded_by_new_run")

    run_id = uuid4()
    pipeline_run = PipelineRunModel(
        id=str(run_id),
        ticket_id=str(ticket_id),
        customer_id=ticket.customer_id,
        status="queued",
        stage="pipeline",
        reason_codes=[],
        deadline_at=deadline_at,
        cost_status="none",
        created_at=now,
        updated_at=now,
    )
    session.add(pipeline_run)

    job = JobModel(
        id=str(uuid4()),
        run_id=str(run_id),
        stage="pipeline",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()

    return RunAccepted(
        id=run_id,
        ticket_id=ticket_id,
        status="queued",
        deadline_at=deadline_at,
    )
