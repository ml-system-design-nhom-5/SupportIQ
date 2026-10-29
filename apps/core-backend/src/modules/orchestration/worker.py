import uuid
from datetime import datetime, timezone, timedelta
from typing import Literal, Any
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_, and_

from src.config import settings
from src.modules.orchestration.models import PipelineRunModel, JobModel, LlmAttemptModel, DraftModel
from src.modules.orchestration.schemas import ClaimedJob
from src.modules.tickets.models import TicketModel

async def claim_next_job(
    session: AsyncSession,
    stage: Literal["pipeline", "llm_egress"],
    worker_id: str,
    lease_seconds: int = 5,
) -> ClaimedJob | None:
    now = datetime.now(timezone.utc)
    stmt = (
        select(JobModel)
        .where(
            JobModel.stage == stage,
            or_(
                JobModel.status == "queued",
                and_(
                    JobModel.status == "running",
                    JobModel.lease_expires_at < now,
                ),
            ),
        )
        .order_by(JobModel.created_at.asc())
        .limit(1)
    )

    if not settings.app_db_url.startswith("sqlite"):
        stmt = stmt.with_for_update(skip_locked=True)

    result = await session.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        return None

    new_lease_token = uuid4()
    job.status = "running"
    job.worker_id = worker_id
    job.lease_token = str(new_lease_token)
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.updated_at = now

    # Also transition run status from queued -> running
    run = await session.get(PipelineRunModel, job.run_id)
    if run and run.status == "queued":
        run.status = "running"
        run.updated_at = now

    await session.commit()

    return ClaimedJob(
        job_id=UUID(job.id),
        run_id=UUID(job.run_id),
        stage=job.stage,
        lease_token=new_lease_token,
        payload=job.payload,
    )

async def complete_pipeline_stage_and_enqueue_egress(
    session: AsyncSession,
    run_id: UUID,
    lease_token: UUID,
    sanitized_payload: dict[str, Any],
) -> bool:
    now = datetime.now(timezone.utc)
    stmt = select(JobModel).where(
        JobModel.run_id == str(run_id),
        JobModel.stage == "pipeline",
        JobModel.lease_token == str(lease_token),
        JobModel.status == "running",
    )
    result = await session.execute(stmt)
    pipeline_job = result.scalar_one_or_none()
    if not pipeline_job:
        return False

    pipeline_job.status = "completed"
    pipeline_job.updated_at = now

    # Create egress job
    egress_job = JobModel(
        id=str(uuid4()),
        run_id=str(run_id),
        stage="llm_egress",
        status="queued",
        payload=sanitized_payload,
        created_at=now,
        updated_at=now,
    )
    session.add(egress_job)
    await session.commit()
    return True

async def commit_run_draft(
    session: AsyncSession,
    run_id: str | UUID,
    lease_token: str | UUID,
    draft_body: str,
    citation_ids: list[str],
) -> bool:
    now = datetime.now(timezone.utc)
    stmt = select(JobModel).where(
        JobModel.run_id == str(run_id),
        JobModel.lease_token == str(lease_token),
        JobModel.status == "running",
    )
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        return False

    # Check if lease expired
    sess_exp = job.lease_expires_at.replace(tzinfo=timezone.utc) if job.lease_expires_at.tzinfo is None else job.lease_expires_at
    if sess_exp < now:
        return False

    run = await session.get(PipelineRunModel, str(run_id))
    if not run or run.status not in ("queued", "running"):
        return False

    # Create draft
    draft_id = str(uuid4())
    draft = DraftModel(
        id=draft_id,
        run_id=str(run_id),
        draft_body=draft_body,
        citation_ids=citation_ids,
        created_at=now,
    )
    session.add(draft)

    run.status = "awaiting_review"
    run.draft_id = draft_id
    run.updated_at = now

    job.status = "completed"
    job.updated_at = now

    # Link run to ticket
    ticket = await session.get(TicketModel, run.ticket_id)
    if ticket:
        ticket.current_run_id = str(run_id)
        ticket.updated_at = now

    await session.commit()
    return True

async def recover_expired_runs_and_attempts(session: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    stmt = select(PipelineRunModel).where(
        PipelineRunModel.status.in_(["queued", "running"]),
        PipelineRunModel.deadline_at < now,
    )
    result = await session.execute(stmt)
    expired_runs = result.scalars().all()

    count = 0
    for run in expired_runs:
        run.status = "escalated"
        reason_codes = list(run.reason_codes or [])
        if "llm_unavailable" not in reason_codes:
            reason_codes.append("llm_unavailable")
        run.reason_codes = reason_codes
        run.cost_status = "unknown"
        run.updated_at = now

        # Mark in-flight jobs as failed
        await session.execute(
            update(JobModel)
            .where(JobModel.run_id == run.id, JobModel.status.in_(["queued", "running"]))
            .values(status="failed", updated_at=now)
        )

        # Mark in-flight attempts as outcome_unknown
        await session.execute(
            update(LlmAttemptModel)
            .where(LlmAttemptModel.run_id == run.id, LlmAttemptModel.status == "in_flight")
            .values(status="outcome_unknown")
        )
        count += 1

    await session.commit()
    return count
