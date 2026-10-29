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
    from src.db import AppSessionLocal
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
