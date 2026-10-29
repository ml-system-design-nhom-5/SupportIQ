import os
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Add apps/core-backend to sys.path so `src...` imports work
core_backend_dir = Path(__file__).resolve().parent.parent / "apps" / "core-backend"
if str(core_backend_dir) not in sys.path:
    sys.path.insert(0, str(core_backend_dir))

# Default test environment variables
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-service-token")
os.environ.setdefault("APP_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-chars-long")
os.environ.setdefault("APP_DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AUDIT_WRITER_DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AUDIT_READER_DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("VAULT_DB_URL", "sqlite+aiosqlite:///:memory:")
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
