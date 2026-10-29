import asyncio
import time
import uuid
from typing import Any
import pytest
from httpx import AsyncClient

from src.main import app
from src.db import AppSessionLocal
from src.modules.orchestration.worker import claim_next_job
from src.modules.orchestration.pipeline_runner import execute_pipeline_job, execute_egress_job

async def simulate_single_session_journey(client: AsyncClient, agent_token: str, ticket_id: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    # 1. Trigger AI run via POST /runs
    run_res = await client.post(
        f"/api/v1/tickets/{ticket_id}/runs",
        json={"mode": "standard"},
        headers={
            "Authorization": f"Bearer {agent_token}",
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": '"1"',
        },
    )
    if run_res.status_code != 202:
        return {"success": False, "status_code": run_res.status_code, "latency": time.perf_counter() - t0}

    run_id = run_res.json()["data"]["id"]

    # 2. Worker processes pipeline stage and egress stage for this run
    from sqlalchemy import select
    from src.modules.orchestration.models import JobModel
    from src.db import get_sqlite_lock

    async with get_sqlite_lock():
        async with AppSessionLocal() as session:
            p_stmt = select(JobModel).where(JobModel.run_id == run_id, JobModel.stage == "pipeline")
            p_res = await session.execute(p_stmt)
            p_job = p_res.scalar_one_or_none()
            if p_job:
                await execute_pipeline_job(session, redis=None, job=p_job)

            e_stmt = select(JobModel).where(JobModel.run_id == run_id, JobModel.stage == "llm_egress")
            e_res = await session.execute(e_stmt)
            e_job = e_res.scalar_one_or_none()
            if e_job:
                await execute_egress_job(session, job=e_job)

    # 3. Check final run status via GET
    status_res = await client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    t_end = time.perf_counter()
    latency = t_end - t0

    is_success = (
        status_res.status_code == 200
        and status_res.json()["data"]["status"] in ("awaiting_review", "escalated")
    )

    return {
        "success": is_success,
        "run_id": run_id,
        "status": status_res.json()["data"]["status"] if status_res.status_code == 200 else "error",
        "latency": latency,
    }

from unittest.mock import patch
from src.modules.llm.schemas import LlmCallOutcome, ValidatedDraft
from src.modules.intent.schemas import IntentPrediction

async def mock_call_via_proxy(*args, **kwargs):
    await asyncio.sleep(0.05)
    return LlmCallOutcome(
        status="completed",
        draft=ValidatedDraft(
            body="Your shipment is in transit and tracked [cit_test_01].",
            citation_ids=["cit_test_01"],
        ),
        cost_micro=1200,
        response_tokens=42,
    )

async def mock_classify_intent(*args, **kwargs):
    await asyncio.sleep(0.02)
    return IntentPrediction(
        intent="track_order",
        confidence=0.98,
        model_version="v1.0.0",
    )

@pytest.mark.asyncio
async def test_load_5_concurrent_sessions(client: AsyncClient, agent_token: str):
    # Verify 5 concurrent sessions load profile (NFR-08)
    concurrency = 5
    latencies: list[float] = []
    successes = 0

    from datetime import datetime, timezone
    from src.modules.tickets.models import TicketModel, MessageModel
    from src.crypto import encrypt_text

    ticket_ids = []
    async with AppSessionLocal() as session:
        now = datetime.now(timezone.utc)
        for _ in range(concurrency):
            t_id = str(uuid.uuid4())
            ticket = TicketModel(
                id=t_id,
                customer_id="a0000000-0000-0000-0000-000000000004",
                assigned_agent_id="a0000000-0000-0000-0000-000000000003",
                handling_queue="standard",
                status="open",
                priority="normal",
                context_version=1,
                version=1,
                created_at=now,
                updated_at=now,
            )
            msg = MessageModel(
                id=str(uuid.uuid4()),
                ticket_id=t_id,
                sender_id="a0000000-0000-0000-0000-000000000004",
                sender_role="customer",
                content_ciphertext=encrypt_text("Where is my delivery? Please check shipping."),
                created_at=now,
            )
            session.add(ticket)
            session.add(msg)
            ticket_ids.append(t_id)
        await session.commit()

    with patch("src.modules.orchestration.pipeline_runner.classify_intent", side_effect=mock_classify_intent), \
         patch("src.modules.orchestration.pipeline_runner.call_via_proxy", side_effect=mock_call_via_proxy):
        tasks = [simulate_single_session_journey(client, agent_token, t_id) for t_id in ticket_ids]
        results = await asyncio.gather(*tasks)

    for r in results:
        if r["success"]:
            successes += 1
        latencies.append(r["latency"])

    latencies.sort()
    n = len(latencies)
    p50 = latencies[int(n * 0.50)]
    p95 = latencies[int(n * 0.95)]
    error_rate = (n - successes) / n

    # Assert SLA targets: p50 <= 4s, p95 <= 12s, error rate <= 1%
    assert p50 <= 4.0, f"p50 exceeded target: {p50}s"
    assert p95 <= 12.0, f"p95 exceeded target: {p95}s"
    assert error_rate <= 0.01, f"error rate exceeded target: {error_rate}"
