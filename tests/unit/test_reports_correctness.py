"""Reproducing tests for report correctness on SQLite (aware/naive datetimes, SQL date bounds, cost accounting)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Account, AuditEntry, Suggestion, Ticket
from argon2 import PasswordHasher
from apps.backend.tickets.reports import report


@pytest.fixture
def sqlite_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database = Database(engine)
    database.create_schema()
    with database.transaction() as session:
        session.add(
            Account(
                account_id="cust-acct-1",
                login_name="customer-1",
                email="customer-1@example.com",
                role="customer",
                display_name="Customer One",
                password_hash=PasswordHasher().hash("pw"),
                is_active=True,
                customer_id="CUST-1",
            )
        )
        session.add(
            Account(
                account_id="mgr-acct-1",
                login_name="manager-1",
                email="manager-1@example.com",
                role="manager",
                display_name="Manager One",
                password_hash=PasswordHasher().hash("pw"),
                is_active=True,
            )
        )
    try:
        yield database
    finally:
        engine.dispose()


def _add_ticket(
    session,
    ticket_id: str,
    created_at: datetime,
    *,
    handling_mode: str = "assisted",
    closed_at: datetime | None = None,
    handling_started_at: datetime | None = None,
):
    session.add(
        Ticket(
            ticket_id=ticket_id,
            customer_id="CUST-1",
            order_id=None,
            status="closed" if closed_at else "open",
            handling_mode=handling_mode,
            is_authority_required=False,
            created_at=created_at,
            handling_started_at=handling_started_at,
            closed_at=closed_at,
            current_suggestion_id=None,
        )
    )


def _add_suggestion(
    session,
    suggestion_id: str,
    ticket_id: str,
    created_at: datetime,
    completed_at: datetime,
    *,
    trigger: str = "ticket_created",
    draft_status: str = "draft_ready",
    analysis_status: str = "ready",
    llm_usage=None,
    llm_metadata=None,
    step_latency_ms=None,
):
    payload = {
        "trigger": trigger,
        "analysis_status": analysis_status,
        "draft_status": draft_status,
        "reason_codes": [],
        "step_latency_ms": step_latency_ms or {"analysis": 100, "draft": 200},
    }
    if llm_usage is not None:
        payload["llm_usage"] = llm_usage
    if llm_metadata is not None:
        payload["llm_metadata"] = llm_metadata
    session.add(
        Suggestion(
            suggestion_id=suggestion_id,
            ticket_id=ticket_id,
            created_at=created_at,
            completed_at=completed_at,
            payload=payload,
            request_payload={},
            pseudonym_map={},
        )
    )


def test_sqlite_report_handles_aware_window_boundaries_and_prior_ticket_latency(sqlite_db):
    start_at = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
    end_at = datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)

    with sqlite_db.transaction() as session:
        # Ticket 1: created before window, closed inside window -> created=0, closed=1, handling=1, e2e latency included
        _add_ticket(
            session,
            "TCK-PRIOR",
            created_at=datetime(2026, 11, 9, 23, 59, 50, tzinfo=timezone.utc),
            handling_started_at=datetime(2026, 11, 10, 0, 1, 0, tzinfo=timezone.utc),
            closed_at=datetime(2026, 11, 10, 0, 1, 5, tzinfo=timezone.utc),
        )
        _add_suggestion(
            session,
            "SG-PRIOR",
            "TCK-PRIOR",
            created_at=datetime(2026, 11, 9, 23, 59, 50, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc),  # exact start_at: included
            llm_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "cost_micro_usd": 0},
        )
        # Ticket 2: created right at end_at (half-open: excluded!)
        _add_ticket(
            session,
            "TCK-END",
            created_at=end_at,
            closed_at=end_at,
        )
        _add_suggestion(
            session,
            "SG-END",
            "TCK-END",
            created_at=end_at,
            completed_at=end_at,  # exact end_at: excluded
            llm_usage={"cost_micro_usd": 99999},
        )
        # Ticket 3: created inside window in +07:00 timezone (= 2026-11-10T10:00:00Z), manual mode
        _add_ticket(
            session,
            "TCK-IN",
            created_at=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc),
            handling_mode="manual",
            handling_started_at=datetime(2026, 11, 10, 10, 0, 10, tzinfo=timezone.utc),
            closed_at=datetime(2026, 11, 10, 10, 0, 20, tzinfo=timezone.utc),
        )
        session.add(
            AuditEntry(
                entry_id="AUD-IN",
                occurred_at=datetime(2026, 11, 10, 0, 1, 5, tzinfo=timezone.utc),
                event_type="decision.recorded",
                actor_account_id="mgr-acct-1",
                ticket_id="TCK-PRIOR",
                trace_id="trace-1",
                data={"decision": "approve"},
            )
        )

    # Query using non-UTC +07:00 offset representing the exact same UTC interval
    tz_plus_7 = timezone(timedelta(hours=7))
    with sqlite_db.transaction() as session:
        res = report(session, start_at.astimezone(tz_plus_7), end_at.astimezone(tz_plus_7))

    assert res["ticket_counts"]["assisted"] == {"created": 0, "closed": 1}
    assert res["ticket_counts"]["manual"] == {"created": 1, "closed": 1}
    assert res["draft_decisions"]["approve"]["count"] == 1
    assert res["end_to_end_latency_ms"]["p50"] == 10000.0
    assert res["handling_time_ms"]["assisted"]["p50"] == 5000.0
    assert res["handling_time_ms"]["manual"]["p50"] == 10000.0
    assert res["llm_cost_micro_usd"] == {
        "total": 0,
        "known_total": 0,
        "average": 0.0,
        "known_average": 0.0,
        "known_count": 1,
        "unknown_count": 0,
    }


def test_cost_accounting_distinguishes_zero_positive_missing_invalid_and_mixed(sqlite_db):
    start_at = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
    end_at = datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)

    # 1. Missing cost metadata (matches live Gemini extraction omitting cost_micro_usd)
    with sqlite_db.transaction() as session:
        _add_ticket(session, "TCK-MISS", created_at=datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc))
        _add_suggestion(
            session,
            "SG-MISS-1",
            "TCK-MISS",
            created_at=datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 1, 0, 2, tzinfo=timezone.utc),
            llm_usage={"input_tokens": 120, "output_tokens": 45, "total_tokens": 165},
            llm_metadata={"model": "gemini-2.5-flash"},
        )
        # Empty llm_usage dict + llm_unavailable should also count as unknown LLM call
        _add_suggestion(
            session,
            "SG-MISS-2",
            "TCK-MISS",
            created_at=datetime(2026, 11, 10, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 1, 1, 2, tzinfo=timezone.utc),
            draft_status="llm_unavailable",
            llm_usage={},
        )
        # Deterministic abstention without LLM call must NOT count as unknown LLM cost
        _add_suggestion(
            session,
            "SG-NO-LLM",
            "TCK-MISS",
            created_at=datetime(2026, 11, 10, 1, 2, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 1, 2, 1, tzinfo=timezone.utc),
            draft_status="abstained",
            llm_usage=None,
        )

    with sqlite_db.transaction() as session:
        missing_only = report(session, start_at, end_at)

    assert missing_only["llm_cost_micro_usd"] == {
        "total": None,
        "known_total": 0,
        "average": None,
        "known_average": None,
        "known_count": 0,
        "unknown_count": 2,
    }

    # 2. Add invalid cost variants (bool, negative, float, string, incomplete flag) + known positive + known 0
    with sqlite_db.transaction() as session:
        invalid_variants = [
            ("SG-BOOL", {"cost_micro_usd": True}),
            ("SG-NEG", {"cost_micro_usd": -10}),
            ("SG-FLOAT", {"cost_micro_usd": 12.5}),
            ("SG-STR", {"cost_micro_usd": "100"}),
            ("SG-INCOMP", {"cost_micro_usd": 500, "usage_incomplete": True}),
        ]
        for idx, (sg_id, usage) in enumerate(invalid_variants, start=3):
            _add_suggestion(
                session,
                sg_id,
                "TCK-MISS",
                created_at=datetime(2026, 11, 10, 1, idx, tzinfo=timezone.utc),
                completed_at=datetime(2026, 11, 10, 1, idx, 1, tzinfo=timezone.utc),
                llm_usage=usage,
            )
        _add_suggestion(
            session,
            "SG-KNOWN-0",
            "TCK-MISS",
            created_at=datetime(2026, 11, 10, 1, 20, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 1, 20, 1, tzinfo=timezone.utc),
            llm_usage={"cost_micro_usd": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )
        _add_suggestion(
            session,
            "SG-KNOWN-POS",
            "TCK-MISS",
            created_at=datetime(2026, 11, 10, 1, 21, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 1, 21, 1, tzinfo=timezone.utc),
            llm_usage={"cost_micro_usd": 3000, "input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
        )

    with sqlite_db.transaction() as session:
        mixed = report(session, start_at, end_at)

    # 2 known (0 + 3000 = 3000, avg 1500.0) and 7 unknown (2 missing + 5 invalid/incomplete)
    assert mixed["llm_cost_micro_usd"] == {
        "total": None,
        "known_total": 3000,
        "average": None,
        "known_average": 1500.0,
        "known_count": 2,
        "unknown_count": 7,
    }


def test_empty_period_zero_llm_calls_has_verified_zero_total(sqlite_db):
    start_at = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
    end_at = datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)
    with sqlite_db.transaction() as session:
        res = report(session, start_at, end_at)
    assert res["llm_cost_micro_usd"] == {
        "total": 0,
        "known_total": 0,
        "average": None,
        "known_average": None,
        "known_count": 0,
        "unknown_count": 0,
    }


def test_console_reports_endpoint_returns_honest_cost_on_sqlite(sqlite_db):
    with sqlite_db.transaction() as session:
        _add_ticket(session, "TCK-HTTP", created_at=datetime(2026, 11, 10, 5, 0, tzinfo=timezone.utc))
        _add_suggestion(
            session,
            "SG-HTTP",
            "TCK-HTTP",
            created_at=datetime(2026, 11, 10, 5, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 5, 0, 1, tzinfo=timezone.utc),
            llm_usage={"input_tokens": 50, "output_tokens": 25, "total_tokens": 75},
        )
    app = create_app(
        settings=Settings(
            database_url_app="sqlite:///:memory:",
            database_url_owner="sqlite:///:memory:",
            allowed_origins=["http://testserver"],
            session_cookie_secure=False,
        ),
        database=sqlite_db,
        start_worker=False,
    )
    client = TestClient(app, headers={"Origin": "http://testserver"})
    login_resp = client.post("/v1/sessions", json={"login_name": "manager-1", "password": "pw"})
    assert login_resp.status_code == 201
    resp = client.get("/v1/console/reports?start_at=2026-11-10T00:00:00Z&end_at=2026-11-11T00:00:00Z")
    assert resp.status_code == 200
    assert resp.json()["llm_cost_micro_usd"] == {
        "total": None,
        "known_total": 0,
        "average": None,
        "known_average": None,
        "known_count": 0,
        "unknown_count": 1,
    }
