import os
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

# Add apps/core-backend to sys.path so `src...` imports work
core_backend_dir = Path(__file__).resolve().parent.parent / "apps" / "core-backend"
if str(core_backend_dir) not in sys.path:
    sys.path.insert(0, str(core_backend_dir))

# Default test environment variables with shared in-memory sqlite
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-service-token")
os.environ.setdefault("APP_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-chars-long")
os.environ.setdefault("APP_DB_URL", "sqlite+aiosqlite:///file:test_app_db?mode=memory&cache=shared&uri=true")
os.environ.setdefault("AUDIT_WRITER_DB_URL", "sqlite+aiosqlite:///file:test_audit_db?mode=memory&cache=shared&uri=true")
os.environ.setdefault("AUDIT_READER_DB_URL", "sqlite+aiosqlite:///file:test_audit_db?mode=memory&cache=shared&uri=true")
os.environ.setdefault("VAULT_DB_URL", "sqlite+aiosqlite:///file:test_vault_db?mode=memory&cache=shared&uri=true")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture
async def client():
    from src.main import app, lifespan
    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    res = await client.post(
        "/api/v1/sessions",
        json={"email": "admin@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    return res.json()["data"]["access_token"]

@pytest_asyncio.fixture
async def manager_token(client: AsyncClient):
    res = await client.post(
        "/api/v1/sessions",
        json={"email": "manager1@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    return res.json()["data"]["access_token"]

@pytest_asyncio.fixture
async def db_session():
    from src.db import Base, app_engine, AppSessionLocal
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in str(app_engine.url):
            from sqlalchemy import text
            await conn.execute(text("CREATE TRIGGER IF NOT EXISTS prevent_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;"))
            await conn.execute(text("CREATE TRIGGER IF NOT EXISTS prevent_audit_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;"))
    async with AppSessionLocal() as session:
        yield session

@pytest_asyncio.fixture
async def agent_token(client: AsyncClient):
    res = await client.post(
        "/api/v1/sessions",
        json={"email": "agent1@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    return res.json()["data"]["access_token"]

@pytest_asyncio.fixture
async def customer_token(client: AsyncClient):
    res = await client.post(
        "/api/v1/sessions",
        json={"email": "customer1@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    return res.json()["data"]["access_token"]

@pytest_asyncio.fixture
async def other_customer_token(client: AsyncClient):
    from src.db import AppSessionLocal
    from src.modules.auth.models import UserModel
    from src.modules.auth.service import hash_password

    async with AppSessionLocal() as session:
        c2 = await session.scalar(select(UserModel).where(UserModel.email == "customer2@supportiq.demo"))
        if not c2:
            c2 = UserModel(
                id="a0000000-0000-0000-0000-000000000005",
                email="customer2@supportiq.demo",
                password_hash=hash_password("DemoPassword123!"),
                role="customer",
                active=True,
                role_version=1,
            )
            session.add(c2)
            await session.commit()

    res = await client.post(
        "/api/v1/sessions",
        json={"email": "customer2@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    return res.json()["data"]["access_token"]

@pytest_asyncio.fixture
async def assigned_ticket_with_draft(client: AsyncClient, agent_token: str, db_session):
    import uuid
    from datetime import datetime, timezone
    from src.modules.tickets.models import TicketModel
    from src.modules.orchestration.models import PipelineRunModel, DraftModel

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
        citation_ids=["cit_01"],
    )
    db_session.add(ticket)
    db_session.add(run)
    db_session.add(draft)
    await db_session.commit()

    return {
        "ticket_id": ticket_id,
        "run_id": run_id,
        "draft_id": draft_id,
        "customer_id": cust_id,
    }
