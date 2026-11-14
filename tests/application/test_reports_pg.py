"""PostgreSQL parity tests for console reports (timezone bounds and unknown/known cost accounting)."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Suggestion, Ticket
from apps.backend.seed import seed
from apps.backend.tickets.reports import report


@pytest.fixture(scope="module")
def pg_report_app():
    secrets_path = Path(os.environ.get("SUPPORTIQ_APPLICATION_SECRETS", ".local/application.json"))
    if not secrets_path.exists():
        pytest.skip("PostgreSQL credentials not found in .local/application.json")
    local = json.loads(secrets_path.read_text())
    owner_url = local["database_url_owner"]
    schema = "test_rep_" + uuid.uuid4().hex
    root = create_engine(owner_url)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = None
    try:
        engine = create_engine(owner_url, connect_args={"options": f"-csearch_path={schema}"})
        database = Database(engine)
        database.create_schema()
        passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
        seed(database, passwords)
        app = create_app(
            settings=Settings(
                database_url_app=local.get("database_url_app", owner_url),
                database_url_owner=owner_url,
                allowed_origins=["http://testserver"],
                session_cookie_secure=False,
            ),
            database=database,
            start_worker=False,
        )
        yield app, passwords, database
    finally:
        if engine is not None:
            engine.dispose()
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def test_postgres_report_boundary_and_unknown_cost_parity(pg_report_app):
    app, passwords, database = pg_report_app
    with database.transaction() as session:
        session.add(
            Ticket(
                ticket_id="TCK-PG-1",
                customer_id="CUST-1001",
                order_id=None,
                status="closed",
                handling_mode="assisted",
                is_authority_required=False,
                created_at=datetime(2026, 11, 12, 2, 0, tzinfo=timezone.utc),
                handling_started_at=datetime(2026, 11, 12, 2, 0, 2, tzinfo=timezone.utc),
                closed_at=datetime(2026, 11, 12, 2, 0, 8, tzinfo=timezone.utc),
                current_suggestion_id=None,
            )
        )
        session.flush()
        session.add(
            Suggestion(
                suggestion_id="SG-PG-1",
                ticket_id="TCK-PG-1",
                created_at=datetime(2026, 11, 12, 2, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 11, 12, 2, 0, 1, tzinfo=timezone.utc),
                payload={
                    "trigger": "ticket_created",
                    "analysis_status": "ready",
                    "draft_status": "draft_ready",
                    "reason_codes": [],
                    "step_latency_ms": {"analysis": 50, "draft": 100},
                    "llm_usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
                },
                request_payload={},
                pseudonym_map={},
            )
        )
        session.add(
            Suggestion(
                suggestion_id="SG-PG-2",
                ticket_id="TCK-PG-1",
                created_at=datetime(2026, 11, 12, 2, 0, 2, tzinfo=timezone.utc),
                completed_at=datetime(2026, 11, 12, 2, 0, 3, tzinfo=timezone.utc),
                payload={
                    "trigger": "retry_draft",
                    "analysis_status": "ready",
                    "draft_status": "draft_ready",
                    "reason_codes": [],
                    "step_latency_ms": {"draft": 90},
                    "llm_usage": {"input_tokens": 40, "output_tokens": 10, "total_tokens": 50, "cost_micro_usd": 1200},
                },
                request_payload={},
                pseudonym_map={},
            )
        )

    tz_plus_7 = timezone(timedelta(hours=7))
    start_at = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc).astimezone(tz_plus_7)
    end_at = datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc).astimezone(tz_plus_7)
    with database.transaction() as session:
        direct = report(session, start_at, end_at)

    assert direct["llm_cost_micro_usd"] == {
        "total": None,
        "known_total": 1200,
        "average": None,
        "known_average": 1200.0,
        "known_count": 1,
        "unknown_count": 1,
    }
    assert direct["end_to_end_latency_ms"]["p50"] == 1000.0
    assert direct["handling_time_ms"]["assisted"]["p50"] == 6000.0

    manager = TestClient(app, headers={"Origin": "http://testserver"})
    assert manager.post("/v1/sessions", json={"login_name": "manager-1", "password": passwords["manager"]}).status_code == 201
    resp = manager.get("/v1/console/reports?start_at=2026-11-12T00:00:00Z&end_at=2026-11-13T00:00:00Z")
    assert resp.status_code == 200
    assert resp.json()["llm_cost_micro_usd"] == direct["llm_cost_micro_usd"]
