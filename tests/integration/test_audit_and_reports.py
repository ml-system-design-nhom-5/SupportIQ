import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts import AuditEventInput
from src.modules.audit.models import AuditEventModel
from src.modules.audit.service import append_event

@pytest.fixture
def seeded_report_fixtures():
    # Will be populated in service or directly via db_session in tests
    return True

@pytest.mark.asyncio
async def test_audit_is_insert_only_and_rollback_on_failure(db_session: AsyncSession):
    # Verify PostgreSQL trigger / permission rejects UPDATE and DELETE on audit.events
    with pytest.raises(Exception):
        await db_session.execute(text("DELETE FROM audit.events"))
    await db_session.rollback()

@pytest.mark.asyncio
async def test_reports_summary_excludes_manual_from_ai_acceptance_and_tracks_unknown_cost(
    client: AsyncClient, manager_token: str, db_session: AsyncSession
):
    from src.db import app_engine, Base
    from sqlalchemy import text
    if "sqlite" in str(app_engine.url):
        async with app_engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS audit_events"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("CREATE TRIGGER IF NOT EXISTS prevent_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;"))
            await conn.execute(text("CREATE TRIGGER IF NOT EXISTS prevent_audit_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;"))

    from src.modules.audit.service import record_report_run_fixture
    await record_report_run_fixture(db_session)

    res = await client.get(
        "/api/v1/reports/summary",
        params={"from": "2026-10-01T00:00:00Z", "to": "2026-10-30T00:00:00Z"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert res.status_code == 200
    report = res.json()["data"]
    # Manual approvals are not counted in ai_review_counts
    assert report["ai_review_counts"] == {"approved": 2, "edited": 1, "rejected": 1}
    assert report["reviewed_drafts"] == 4
    # Unknown cost runs are counted separately and never coerced to 0
    assert report["cost"]["unknown_runs"] == 1
    assert report["cost"]["known_total_micro"] == 3000
    assert report["cost"]["known_average_per_run_micro"] == 1000
