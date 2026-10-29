import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.modules.tickets.models import TicketModel, MessageModel
from src.modules.orchestration.models import PipelineRunModel, DraftModel
from src.modules.commerce.models import OrderModel
from src.modules.review.models import ReviewDecisionModel

@pytest_asyncio.fixture
async def assigned_ticket_with_draft(client: AsyncClient, agent_token: str, db_session: AsyncSession):
    # Agent user id: a0000000-0000-0000-0000-000000000003
    agent_id = "a0000000-0000-0000-0000-000000000003"
    cust_id = "a0000000-0000-0000-0000-000000000004"
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    draft_id = str(uuid.uuid4())

    ticket = TicketModel(
        id=ticket_id,
        customer_id=cust_id,
        assigned_agent_id=agent_id,
        handling_queue="standard",
        status="open",
        priority="normal",
        context_version=1,
        version=2,
        current_run_id=run_id,
        current_decision_id=None,
        created_at=now,
        updated_at=now,
    )
    run = PipelineRunModel(
        id=run_id,
        ticket_id=ticket_id,
        customer_id=cust_id,
        status="awaiting_review",
        stage="llm_egress",
        reason_codes=[],
        deadline_at=now,
        cost_status="known",
        cost_micro=1200,
        draft_id=draft_id,
        created_at=now,
        updated_at=now,
    )
    draft = DraftModel(
        id=draft_id,
        run_id=run_id,
        draft_body="Draft AI response for order status.",
        citation_ids=["k1"],
        created_at=now,
    )
    db_session.add(ticket)
    db_session.add(run)
    db_session.add(draft)
    await db_session.commit()
    return {"ticket_id": ticket_id, "draft_id": draft_id, "run_id": run_id}

@pytest_asyncio.fixture
async def assigned_open_ticket(client: AsyncClient, agent_token: str, db_session: AsyncSession):
    agent_id = "a0000000-0000-0000-0000-000000000003"
    cust_id = "a0000000-0000-0000-0000-000000000004"
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())

    ticket = TicketModel(
        id=ticket_id,
        customer_id=cust_id,
        assigned_agent_id=agent_id,
        handling_queue="standard",
        status="open",
        priority="normal",
        context_version=1,
        version=2,
        current_run_id=None,
        current_decision_id=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(ticket)
    await db_session.commit()
    return {"id": ticket_id}

@pytest.fixture
def down_ai_and_resolver():
    return True

@pytest_asyncio.fixture
async def approved_decision_with_order_snapshot(db_session: AsyncSession):
    agent_id = "a0000000-0000-0000-0000-000000000003"
    cust_id = "a0000000-0000-0000-0000-000000000004"
    now = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())
    ticket_id = str(uuid.uuid4())
    dec_id = str(uuid.uuid4())

    order = OrderModel(
        id=order_id,
        customer_id=cust_id,
        status="placed",
        total_minor=500000,
        currency="VND",
        demo=True,
        created_at=now,
        updated_at=now,
    )
    ticket = TicketModel(
        id=ticket_id,
        customer_id=cust_id,
        order_id=order_id,
        assigned_agent_id=agent_id,
        handling_queue="standard",
        status="open",
        priority="normal",
        context_version=1,
        version=3,
        current_run_id=None,
        current_decision_id=dec_id,
        created_at=now,
        updated_at=now,
    )
    decision = ReviewDecisionModel(
        id=dec_id,
        ticket_id=ticket_id,
        actor_id=agent_id,
        source="manual",
        action="approve",
        body="Your order is confirmed.",
        reason="Manual approval",
        order_version=1,
        created_at=now,
    )
    db_session.add(order)
    db_session.add(ticket)
    db_session.add(decision)
    await db_session.commit()
    return {"ticket_id": ticket_id, "order_id": order_id, "decision_id": dec_id}

@pytest.fixture
def bump_order_version(db_session: AsyncSession):
    async def _bump(order_id: str):
        now = datetime.now(timezone.utc)
        await db_session.execute(
            update(OrderModel)
            .where(OrderModel.id == str(order_id))
            .values(status="shipped", updated_at=now)
        )
        await db_session.commit()
    return _bump

@pytest.mark.asyncio
async def test_send_reply_rejects_stale_approval_after_reject_or_new_message(
    client: AsyncClient, agent_token: str, assigned_ticket_with_draft
):
    t_id = assigned_ticket_with_draft["ticket_id"]
    draft_id = assigned_ticket_with_draft["draft_id"]

    # 1. Agent approves draft -> creates Decision D1, does NOT create a public reply
    d1_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={"source": "ai", "action": "approve", "draft_id": draft_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'},
    )
    assert d1_res.status_code == 201
    d1_id = d1_res.json()["data"]["id"]

    # 2. Agent subsequently rejects the same draft -> clears current_decision_id
    d2_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={"source": "ai", "action": "reject", "draft_id": draft_id, "reason": "Outdated policy"},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"3"'},
    )
    assert d2_res.status_code == 201

    # 3. Attempting to send D1 must fail with 409 state_conflict
    send_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": d1_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"4"'},
    )
    assert send_res.status_code == 409
    assert send_res.json()["code"] == "state_conflict"

@pytest.mark.asyncio
async def test_manual_approval_and_send_succeed_when_ai_and_resolver_down(
    client: AsyncClient, agent_token: str, customer_token: str, assigned_open_ticket, down_ai_and_resolver
):
    t_id = assigned_open_ticket["id"]
    dec_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={
            "source": "manual",
            "action": "approve",
            "body": "Your order is currently in transit and will arrive tomorrow.",
            "reason": "Verified directly from order table during AI outage",
        },
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'},
    )
    assert dec_res.status_code == 201
    dec_id = dec_res.json()["data"]["id"]

    reply_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": dec_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"3"'},
    )
    assert reply_res.status_code == 201

    # Customer now sees the outbound reply
    msgs = (await client.get(f"/api/v1/tickets/{t_id}/messages", headers={"Authorization": f"Bearer {customer_token}"})).json()["data"]
    assert any(m["direction"] == "outbound" and "in transit" in m["body"] for m in msgs)

@pytest.mark.asyncio
async def test_send_reply_fails_with_409_when_order_version_changes(
    client: AsyncClient, agent_token: str, approved_decision_with_order_snapshot, bump_order_version
):
    t_id = approved_decision_with_order_snapshot["ticket_id"]
    dec_id = approved_decision_with_order_snapshot["decision_id"]
    await bump_order_version(approved_decision_with_order_snapshot["order_id"])

    send_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": dec_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"3"'},
    )
    assert send_res.status_code == 409
    assert send_res.json()["code"] == "evidence_changed"
