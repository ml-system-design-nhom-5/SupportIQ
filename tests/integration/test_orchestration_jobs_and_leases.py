import uuid
from datetime import datetime, timezone, timedelta
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.orchestration.worker import (
    claim_next_job,
    commit_run_draft,
    recover_expired_runs_and_attempts,
)
from src.modules.orchestration.models import PipelineRunModel, JobModel, LlmAttemptModel

@pytest_asyncio.fixture
async def queued_run_fixture(db_session: AsyncSession):
    now = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())
    run = PipelineRunModel(
        id=run_id,
        ticket_id=str(uuid.uuid4()),
        customer_id=str(uuid.uuid4()),
        status="queued",
        stage="pipeline",
        reason_codes=[],
        deadline_at=now + timedelta(seconds=12),
        cost_status="none",
        created_at=now,
        updated_at=now,
    )
    job = JobModel(
        id=str(uuid.uuid4()),
        run_id=run_id,
        stage="pipeline",
        status="queued",
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.add(job)
    await db_session.commit()
    return run

@pytest_asyncio.fixture
async def in_flight_expired_egress_fixture(db_session: AsyncSession):
    past = datetime.now(timezone.utc) - timedelta(seconds=20)
    run_id = str(uuid.uuid4())
    run = PipelineRunModel(
        id=run_id,
        ticket_id=str(uuid.uuid4()),
        customer_id=str(uuid.uuid4()),
        status="running",
        stage="llm_egress",
        reason_codes=[],
        deadline_at=past,
        cost_status="none",
        created_at=past,
        updated_at=past,
    )
    job = JobModel(
        id=str(uuid.uuid4()),
        run_id=run_id,
        stage="llm_egress",
        status="running",
        worker_id="w-old",
        lease_token=str(uuid.uuid4()),
        lease_expires_at=past,
        created_at=past,
        updated_at=past,
    )
    attempt = LlmAttemptModel(
        id=str(uuid.uuid4()),
        run_id=run_id,
        attempt_no=1,
        status="in_flight",
        created_at=past,
    )
    db_session.add(run)
    db_session.add(job)
    db_session.add(attempt)
    await db_session.commit()
    return run

@pytest.mark.asyncio
async def test_stale_lease_token_cannot_overwrite_superseded_run(db_session: AsyncSession, queued_run_fixture):
    run_id = queued_run_fixture.id
    claimed_1 = await claim_next_job(db_session, stage="pipeline", worker_id="w1", lease_seconds=0)
    assert claimed_1 is not None

    # Lease expires and worker 2 claims the job with a new lease_token
    claimed_2 = await claim_next_job(db_session, stage="pipeline", worker_id="w2", lease_seconds=10)
    assert claimed_2 is not None
    assert claimed_2.lease_token != claimed_1.lease_token

    # Worker 1 tries to commit late with old lease_token -> rejected
    committed = await commit_run_draft(
        db_session, run_id=run_id, lease_token=claimed_1.lease_token, draft_body="Late draft", citation_ids=["c1"]
    )
    assert committed is False

@pytest.mark.asyncio
async def test_recover_in_flight_llm_attempt_marks_outcome_unknown_without_retry(
    db_session: AsyncSession, in_flight_expired_egress_fixture
):
    run_id = in_flight_expired_egress_fixture.id
    recovered = await recover_expired_runs_and_attempts(db_session)
    assert recovered == 1

    run = await db_session.get(type(in_flight_expired_egress_fixture), run_id)
    assert run.status == "escalated"
    assert "llm_unavailable" in run.reason_codes
    assert run.cost_status == "unknown"
