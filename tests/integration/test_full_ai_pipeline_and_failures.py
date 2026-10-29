import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select, func

from src.crypto import encrypt_text
from src.modules.orchestration.pipeline_runner import execute_pipeline_job, execute_egress_job
from src.modules.orchestration.worker import claim_next_job
from src.modules.orchestration.models import PipelineRunModel, JobModel, ReleaseManifestModel
from src.modules.tickets.models import TicketModel, MessageModel
from src.modules.retrieval.models import KnowledgeDocumentModel, KnowledgeDocumentVersionModel
from src.modules.review.models import ReplyModel

@pytest.fixture
async def queued_order_tracking_run(db_session):
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    customer_id = "a0000000-0000-0000-0000-000000000004"

    # Ticket & message
    ticket = TicketModel(
        id=ticket_id,
        customer_id=customer_id,
        handling_queue="standard",
        status="open",
        priority="normal",
        context_version=1,
        version=1,
        current_run_id=run_id,
        current_decision_id=None,
        created_at=now,
        updated_at=now,
    )
    msg = MessageModel(
        id=str(uuid.uuid4()),
        ticket_id=ticket_id,
        sender_id=customer_id,
        sender_role="customer",
        content_ciphertext=encrypt_text("Where is my package? Track my order status please."),
        created_at=now,
    )
    db_session.add(ticket)
    db_session.add(msg)

    # Active release manifest
    release = ReleaseManifestModel(
        id=str(uuid.uuid4()),
        release_tag=f"rel-pipeline-{uuid.uuid4()}",
        intent_model_name="bitext-intent-classifier",
        intent_model_version="v1.0.0",
        embedding_model_name="text-embedding-3-small",
        embedding_model_version="v1.0.0",
        llm_model_name="gpt-4o-mini",
        prompt_template_hash="a" * 64,
        active=True,
    )
    db_session.add(release)

    # Approved knowledge document
    doc_id = str(uuid.uuid4())
    kb_doc = KnowledgeDocumentModel(id=doc_id, title="Order Tracking Policy", category="policy")
    kb_ver = KnowledgeDocumentVersionModel(
        id=str(uuid.uuid4()),
        document_id=doc_id,
        version=1,
        policy_key="track_order",
        normalized_rule_value="tracking_portal",
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=365),
        status="approved",
        allowed_roles=["agent", "staff", "manager", "admin"],
        content_hash="hash_track_01",
        sanitized_excerpt="Customers can track order packages directly from their account portal.",
    )
    db_session.add(kb_doc)
    db_session.add(kb_ver)

    # Pipeline Run & Job
    run = PipelineRunModel(
        id=run_id,
        ticket_id=ticket_id,
        customer_id=customer_id,
        status="queued",
        stage="pipeline",
        reason_codes=[],
        deadline_at=now + timedelta(seconds=12),
        cost_status="none",
        release_id=release.id,
        created_at=now,
        updated_at=now,
    )
    job = JobModel(
        id=str(uuid.uuid4()),
        run_id=run_id,
        stage="pipeline",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(run)

    return run

@pytest.mark.asyncio
async def test_end_to_end_pipeline_creates_grounded_draft_without_auto_reply(
    db_session, redis_client, queued_order_tracking_run
):
    run_id = queued_order_tracking_run.id
    p_job = await claim_next_job(db_session, stage="pipeline", worker_id="w1")
    assert p_job is not None
    await execute_pipeline_job(db_session, redis_client, p_job)

    e_job = await claim_next_job(db_session, stage="llm_egress", worker_id="w2")
    assert e_job is not None
    await execute_egress_job(db_session, e_job)

    await db_session.refresh(queued_order_tracking_run)
    assert queued_order_tracking_run.status == "awaiting_review"
    assert queued_order_tracking_run.draft is not None
    assert len(queued_order_tracking_run.draft.citation_ids) >= 1

    # Invariant #1: Worker never creates a public reply
    reply_count = await db_session.scalar(
        select(func.count()).select_from(ReplyModel).where(ReplyModel.ticket_id == queued_order_tracking_run.ticket_id)
    )
    assert reply_count == 0

@pytest.mark.asyncio
async def test_deadline_exceeded_escalates_run(db_session, redis_client):
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    customer_id = "a0000000-0000-0000-0000-000000000004"

    ticket = TicketModel(
        id=ticket_id,
        customer_id=customer_id,
        handling_queue="standard",
        status="open",
        priority="normal",
        context_version=1,
        version=1,
        current_run_id=run_id,
        current_decision_id=None,
        created_at=now,
        updated_at=now,
    )
    # Expired run (deadline was 10 seconds ago)
    run = PipelineRunModel(
        id=run_id,
        ticket_id=ticket_id,
        customer_id=customer_id,
        status="running",
        stage="llm_egress",
        reason_codes=[],
        deadline_at=now - timedelta(seconds=10),
        cost_status="none",
        created_at=now - timedelta(seconds=20),
        updated_at=now,
    )
    job = JobModel(
        id=str(uuid.uuid4()),
        run_id=run_id,
        stage="llm_egress",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db_session.add(ticket)
    db_session.add(run)
    db_session.add(job)
    await db_session.commit()

    e_job = await claim_next_job(db_session, stage="llm_egress", worker_id="w3")
    assert e_job is not None
    await execute_egress_job(db_session, e_job)

    await db_session.refresh(run)
    assert run.status == "escalated"
    assert "deadline_exceeded" in run.reason_codes
