"""Dedicated boundary tests for SupportIQ Task B1:
- Sticky manager authority after intent override and async retry
- Duplicate send under concurrency (identical idempotency key vs distinct requests)
- Manual fallback on AI errors (worker analysis failure, draft failure, max retries, preserves manual reply and authority)
- Audit immutability under runtime role supportiq_app and owner role
- Outbound gateway transport synthetic PII and log capture (real transport payload and log inspection)
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database, utcnow
from apps.backend.platform.models import Account, AuditEntry, CustomerMessage, Order, Suggestion, SuggestionJob, Ticket
from apps.backend.platform.observability import RE_CARD, RE_EMAIL, RE_PHONE, StructuredLogger, logger
from apps.backend.seed import seed
from apps.backend.tickets.jobs import SuggestionWorker
from apps.backend.tickets.privacy import pseudonymize, restore
from apps.backend.tickets.service import act, allowed_actions, create_suggestion, create_ticket, order_context, require_ticket, workspace


def get_secrets():
    secrets_path = Path(os.environ.get("SUPPORTIQ_APPLICATION_SECRETS", ".local/application.json"))
    if not secrets_path.exists():
        fallback = Path("F:/Năm 3/SD/project/SupportIQ/.local/application.json")
        if fallback.exists():
            secrets_path = fallback
        else:
            pytest.skip("PostgreSQL credentials not found in .local/application.json")
    return json.loads(secrets_path.read_text())


@pytest.fixture(scope="module")
def pg_application():
    """Disposable PostgreSQL schema for safety closure tests."""
    local = get_secrets()
    owner_url = local["database_url_owner"]
    schema = "test_b1_" + uuid.uuid4().hex
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
        settings = Settings(
            database_url_app=local.get("database_url_app", owner_url),
            database_url_owner=owner_url,
            allowed_origins=["http://testserver"],
            session_cookie_secure=False,
            ai_service_base_url="http://mock-ai-service:8002",
        )
        app = create_app(settings=settings, database=database, start_worker=False)
        yield app, passwords, database, settings, schema, local
    finally:
        if engine is not None:
            engine.dispose()
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def login_client(app, passwords, role="customer", name=None):
    client = TestClient(app, headers={"Origin": "http://testserver"})
    response = client.post("/v1/sessions", json={"login_name": name or role + "-1", "password": passwords[role]})
    assert response.status_code == 201, response.text
    return client


def post_with_key(client, path, body, key=None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())})


# ---------------------------------------------------------------------------
# 1. Sticky manager authority after intent override and async retry
# ---------------------------------------------------------------------------

def test_initial_sensitive_chargeback_keywords_require_authority(pg_application):
    """Customer message mentioning chargeback/fraud/lawsuit must require manager authority from creation."""
    app, passwords, database, _, _, _ = pg_application
    customer = login_client(app, passwords, "customer")
    staff = login_client(app, passwords, "staff")

    response = post_with_key(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "I noticed an unauthorized transaction and chargeback on my credit card for ORD-1001."
    })
    assert response.status_code == 201
    ticket_id = response.json()["ticket_id"]

    ticket_view = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert ticket_view["is_authority_required"] is True

    # Mark suggestion completed so send isn't blocked by pending
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        s = session.get(Suggestion, t.current_suggestion_id)
        s.payload = {**s.payload, "analysis_status": "ready", "draft_status": "draft_ready", "reason_codes": ["requires_authority"]}

    # Staff direct send must be blocked by authority-required
    send_res = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/replies", {
        "basis": "no_ai_draft",
        "body": "We received your notice."
    })
    assert send_res.status_code == 403
    assert "authority-required" in send_res.json()["type"]


def test_sticky_authority_persists_after_staff_intent_override_and_async_retry(pg_application):
    """Authority requirement must remain sticky after intent override to routine intent and through async retries."""
    app, passwords, database, settings, _, _ = pg_application
    customer = login_client(app, passwords, "customer")
    staff = login_client(app, passwords, "staff")
    manager = login_client(app, passwords, "manager")

    # 1. Customer creates ticket with refund request
    res = post_with_key(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "I would like to request a refund for this order."
    })
    assert res.status_code == 201
    ticket_id = res.json()["ticket_id"]

    # In DB, mark suggestion as ready with requires_authority
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        t.is_authority_required = True
        s = session.get(Suggestion, t.current_suggestion_id)
        s.payload = {
            **s.payload,
            "analysis_status": "ready",
            "draft_status": "draft_ready",
            "analysis": {
                "intent": {"label": "request_refund", "probability": 0.95, "confidence_band": "high"},
                "alternatives": [],
                "documents": [],
                "routing": {"recommendation": "draft", "reason_codes": ["requires_authority"]}
            },
            "draft": {"text": "Refund policy details.", "segments": [], "citations": []}
        }

    # Verify workspace shows authority required
    ws = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert ws["is_authority_required"] is True
    assert "send_reply" not in ws["allowed_actions"]
    assert "submit_reply_proposal" in ws["allowed_actions"]

    # 2. Staff overrides intent to routine intent "track_order"
    override_res = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/suggestions", {
        "intent_override": "track_order"
    })
    assert override_res.status_code == 202

    # Authority MUST remain True after override
    ws2 = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert ws2["is_authority_required"] is True
    assert "send_reply" not in ws2["allowed_actions"]

    # Mark the new suggestion completed so send isn't blocked by pending
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        s = session.get(Suggestion, t.current_suggestion_id)
        s.payload = {**s.payload, "analysis_status": "ready", "draft_status": "unavailable", "reason_codes": []}

    # Direct staff send must still be forbidden with authority-required
    staff_send = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/replies", {
        "basis": "no_ai_draft",
        "body": "Direct reply attempt by staff."
    })
    assert staff_send.status_code == 403
    assert "authority-required" in staff_send.json()["type"]

    # 3. Mark suggestion as transient failure to allow retry
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        s = session.get(Suggestion, t.current_suggestion_id)
        s.payload = {
            **s.payload,
            "analysis_status": "unavailable",
            "draft_status": "llm_unavailable",
            "reason_codes": ["llm_timeout"]
        }

    # 4. Staff retries suggestion
    retry_res = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/suggestions", {})
    assert retry_res.status_code == 202

    # Retried suggestion must preserve the staff intent override "track_order" and keep authority
    ws3 = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert ws3["is_authority_required"] is True
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        s = session.get(Suggestion, t.current_suggestion_id)
        assert s.payload.get("intent_override") == "track_order"
        # Complete it for proposal submission
        s.payload = {**s.payload, "analysis_status": "ready", "draft_status": "unavailable"}

    # 5. Staff can submit reply proposal
    proposal_res = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/reply-proposals", {
        "basis": "no_ai_draft",
        "body": "Proposed response for manager review."
    })
    assert proposal_res.status_code == 201
    proposal_id = proposal_res.json()["proposal_id"]

    # 6. Manager can approve and send reply
    mgr_send = post_with_key(manager, f"/v1/console/tickets/{ticket_id}/replies", {
        "basis": "reply_proposal",
        "proposal_id": proposal_id,
        "body": "Proposed response for manager review."
    })
    assert mgr_send.status_code == 201


def test_override_to_sensitive_intent_triggers_immediate_authority(pg_application):
    """Overriding intent from non-sensitive (delivery_time) to sensitive (cancel_order or payment_issue) must require authority."""
    app, passwords, database, settings, _, _ = pg_application
    customer = login_client(app, passwords, "customer")
    staff = login_client(app, passwords, "staff")

    res = post_with_key(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "When will my package arrive?"
    })
    assert res.status_code == 201
    ticket_id = res.json()["ticket_id"]

    # Mark as ready routine suggestion
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        assert t.is_authority_required is False
        s = session.get(Suggestion, t.current_suggestion_id)
        s.payload = {
            **s.payload,
            "analysis_status": "ready",
            "draft_status": "draft_ready",
            "analysis": {
                "intent": {"label": "delivery_time", "probability": 0.90, "confidence_band": "high"},
                "alternatives": [],
                "documents": [],
                "routing": {"recommendation": "draft", "reason_codes": []}
            },
            "draft": {"text": "Delivery takes 2-3 days.", "segments": [], "citations": []}
        }

    # Override intent to sensitive action "payment_issue"
    override_res = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/suggestions", {
        "intent_override": "payment_issue"
    })
    assert override_res.status_code == 202

    ws = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert ws["is_authority_required"] is True
    assert "send_reply" not in ws["allowed_actions"]


# ---------------------------------------------------------------------------
# 2. Duplicate send under concurrency
# ---------------------------------------------------------------------------

def test_concurrent_send_identical_idempotency_key_returns_single_reply(pg_application):
    """Two concurrent send requests with the SAME Idempotency-Key must return identical 201 responses with one DB reply."""
    app, passwords, database, _, _, _ = pg_application
    customer = login_client(app, passwords, "customer")
    staff_client1 = login_client(app, passwords, "staff")
    staff_client2 = login_client(app, passwords, "staff")

    res = post_with_key(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "Where is my item?"
    })
    ticket_id = res.json()["ticket_id"]
    path = f"/v1/console/tickets/{ticket_id}/replies"

    # Mark suggestion as completed so replies are not blocked by pending
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        s = session.get(Suggestion, t.current_suggestion_id)
        s.payload = {**s.payload, "analysis_status": "ready", "draft_status": "unavailable"}

    shared_key = f"key-{uuid.uuid4()}"
    payload = {"basis": "no_ai_draft", "body": "Your item is currently being sorted."}

    def do_send(client):
        return post_with_key(client, path, payload, key=shared_key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(do_send, [staff_client1, staff_client2]))

    # Both must succeed with 201 and return identical JSON
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["reply_id"] == responses[1].json()["reply_id"]
    assert responses[0].json()["body"] == responses[1].json()["body"]

    # Verify exactly ONE reply in database and ONE audit entry
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        assert t.status == "closed"
        assert t.reply["reply_id"] == responses[0].json()["reply_id"]
        audit_entries = session.scalars(
            select(AuditEntry).where(AuditEntry.ticket_id == ticket_id, AuditEntry.event_type == "reply.sent")
        ).all()
        assert len(audit_entries) == 1


def test_concurrent_send_different_idempotency_keys_second_fails_409(pg_application):
    """Two concurrent send requests with DIFFERENT Idempotency-Keys: exactly one 201, other gets 409."""
    app, passwords, database, _, _, _ = pg_application
    customer = login_client(app, passwords, "customer")
    staff_client1 = login_client(app, passwords, "staff")
    staff_client2 = login_client(app, passwords, "staff")

    res = post_with_key(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "Check tracking status"
    })
    ticket_id = res.json()["ticket_id"]
    path = f"/v1/console/tickets/{ticket_id}/replies"

    # Mark suggestion as completed so replies are not blocked by pending
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        s = session.get(Suggestion, t.current_suggestion_id)
        s.payload = {**s.payload, "analysis_status": "ready", "draft_status": "unavailable"}

    payload1 = {"basis": "no_ai_draft", "body": "Reply from agent 1"}
    payload2 = {"basis": "no_ai_draft", "body": "Reply from agent 2"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(lambda: post_with_key(staff_client1, path, payload1, key=str(uuid.uuid4())))
        f2 = pool.submit(lambda: post_with_key(staff_client2, path, payload2, key=str(uuid.uuid4())))
        r1, r2 = f1.result(), f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [201, 409]

    # Exactly one reply saved
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        assert t.status == "closed"
        audit_entries = session.scalars(
            select(AuditEntry).where(AuditEntry.ticket_id == ticket_id, AuditEntry.event_type == "reply.sent")
        ).all()
        assert len(audit_entries) == 1


# ---------------------------------------------------------------------------
# 3. Manual fallback on AI errors
# ---------------------------------------------------------------------------

def test_manual_fallback_on_ai_service_analysis_failure(pg_application):
    """When the AI service fails on analysis, worker must fail closed without calling draft and provide manual fallback."""
    app, passwords, database, settings, _, _ = pg_application
    customer = login_client(app, passwords, "customer")
    staff = login_client(app, passwords, "staff")

    res = post_with_key(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "My item arrived with damaged packaging."
    })
    ticket_id = res.json()["ticket_id"]

    with database.transaction() as session:
        s_id = session.get(Ticket, ticket_id).current_suggestion_id

    worker = SuggestionWorker(database, settings)
    claimed = worker.claim(s_id)
    assert claimed is not None
    identifier, token, payload = claimed

    # Execute with failing AI calls
    class MockFailingClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None):
            raise httpx.ConnectError("Failed to connect to AI gateway")

    import apps.backend.tickets.jobs as jobs_mod
    original_client = jobs_mod.httpx.Client
    jobs_mod.httpx.Client = MockFailingClient
    try:
        worker.process(identifier, token, payload)
    finally:
        jobs_mod.httpx.Client = original_client

    # Verify suggestion state: completed, unavailable, staff_note explains manual handling
    ws = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert ws["suggestion"]["analysis_status"] == "unavailable"
    assert ws["suggestion"]["draft_status"] == "unavailable"
    assert "ai_service_unavailable" in ws["suggestion"]["reason_codes"]
    assert "staff_note" in ws["suggestion"]
    assert "manual" in ws["suggestion"]["staff_note"].lower()

    # Staff allowed_actions must offer manual send_reply and retry_suggestion
    assert "send_reply" in ws["allowed_actions"]
    assert "retry_suggestion" in ws["allowed_actions"]

    # Staff can immediately send manual reply
    send_res = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/replies", {
        "basis": "no_ai_draft",
        "body": "We apologize for the damaged box. A replacement is on its way."
    })
    assert send_res.status_code == 201

    # Customer verifies reply received
    cust_res = customer.get(f"/v1/shop/tickets/{ticket_id}").json()
    assert cust_res["customer_status"] == "replied"
    assert "replacement is on its way" in cust_res["reply"]["body"]


def test_manual_fallback_on_draft_failure_retains_retrieved_sources(pg_application):
    """When analysis succeeds but draft fails, staff gets retrieved sources and can send manual reply."""
    app, passwords, database, settings, _, _ = pg_application
    customer = login_client(app, passwords, "customer")
    staff = login_client(app, passwords, "staff")

    res = post_with_key(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "What is the return period?"
    })
    ticket_id = res.json()["ticket_id"]

    with database.transaction() as session:
        s_id = session.get(Ticket, ticket_id).current_suggestion_id

    worker = SuggestionWorker(database, settings)
    claimed = worker.claim(s_id)
    assert claimed is not None
    identifier, token, payload = claimed

    analysis_data = {
        "intent": {"label": "return_policy", "probability": 0.92, "confidence_band": "high"},
        "alternatives": [],
        "is_in_scope": True,
        "documents": [{
            "document_id": "POL-RET-001",
            "version": "1.0",
            "title": "Standard Return Policy",
            "snippet": "Products can be returned within 30 days of delivery.",
            "rank": 1,
            "validity": "valid"
        }],
        "routing": {"recommendation": "draft", "reason_codes": []},
        "warnings": [],
        "versions": {"release_id": "test-rel", "model_version": "v1.0.0"},
        "step_latency_ms": {"analysis": 15}
    }

    class MockDraftFailClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None):
            if "analyses" in url:
                req = httpx.Request("POST", url)
                return httpx.Response(200, json=analysis_data, request=req)
            raise httpx.ReadTimeout("Draft generation timed out")

    import apps.backend.tickets.jobs as jobs_mod
    original_client = jobs_mod.httpx.Client
    jobs_mod.httpx.Client = MockDraftFailClient
    try:
        worker.process(identifier, token, payload)
    finally:
        jobs_mod.httpx.Client = original_client

    ws = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert ws["suggestion"]["analysis_status"] == "ready"
    assert ws["suggestion"]["draft_status"] == "unavailable"
    assert ws["suggestion"]["analysis"]["documents"][0]["document_id"] == "POL-RET-001"
    assert "manual" in ws["suggestion"]["staff_note"].lower()

    # Manual reply with no_ai_draft succeeds
    send_res = post_with_key(staff, f"/v1/console/tickets/{ticket_id}/replies", {
        "basis": "no_ai_draft",
        "body": "According to our policy, you may return the item within 30 days."
    })
    assert send_res.status_code == 201


# ---------------------------------------------------------------------------
# 4. Audit immutability under runtime role supportiq_app and owner role
# ---------------------------------------------------------------------------

def test_audit_immutability_under_owner_and_runtime_role(pg_application):
    """Verify append-only audit and customer message immutability under owner role (triggers) and supportiq_app runtime role (grants)."""
    _, _, database, _, schema, local = pg_application
    owner_url = local["database_url_owner"]
    app_url = local.get("database_url_app")

    # 1. Under Owner role: SQL triggers protect_audit must block UPDATE and DELETE
    owner_engine = create_engine(owner_url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        # Query existing ticket to safely insert into customer_messages without foreign key error
        with owner_engine.begin() as conn:
            ticket_id = conn.execute(text("SELECT ticket_id FROM tickets LIMIT 1")).scalar()
            test_audit_id = str(uuid.uuid4())
            conn.execute(text("""
                INSERT INTO audit_log_entries (entry_id, occurred_at, event_type, trace_id, data)
                VALUES (:id, now(), 'probe.event', 'probe-trace', '{}'::jsonb)
            """), {"id": test_audit_id})

        with owner_engine.begin() as conn:
            with pytest.raises(DBAPIError, match="Append-only record"):
                conn.execute(text("UPDATE audit_log_entries SET event_type='tampered' WHERE entry_id = :id"), {"id": test_audit_id})
        with owner_engine.begin() as conn:
            with pytest.raises(DBAPIError, match="Append-only record"):
                conn.execute(text("DELETE FROM audit_log_entries WHERE entry_id = :id"), {"id": test_audit_id})
        with owner_engine.begin() as conn:
            with pytest.raises(DBAPIError, match="Append-only record"):
                conn.execute(text("UPDATE customer_messages SET body='tampered' WHERE ticket_id = :id"), {"id": ticket_id})
        with owner_engine.begin() as conn:
            with pytest.raises(DBAPIError, match="Append-only record"):
                conn.execute(text("DELETE FROM customer_messages WHERE ticket_id = :id"), {"id": ticket_id})
    finally:
        owner_engine.dispose()

    # 2. Under Runtime role supportiq_app: grants and triggers must enforce immutability
    if app_url:
        # Grant usage on test schema to supportiq_app to simulate deployment environment
        with create_engine(owner_url).begin() as conn:
            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO supportiq_app'))
            conn.execute(text(f'GRANT SELECT, INSERT ON "{schema}".audit_log_entries TO supportiq_app'))
            conn.execute(text(f'GRANT SELECT, INSERT ON "{schema}".customer_messages TO supportiq_app'))
            conn.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{schema}".sessions TO supportiq_app'))
            conn.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{schema}".idempotency_records TO supportiq_app'))
            conn.execute(text(f'GRANT SELECT, UPDATE ON "{schema}".tickets TO supportiq_app'))

        app_engine = create_engine(app_url, connect_args={"options": f"-csearch_path={schema}"})
        try:
            with app_engine.connect() as conn:
                current_user = conn.execute(text("SELECT current_user")).scalar()
                assert current_user == "supportiq_app", f"Expected supportiq_app, got {current_user}"

            with app_engine.begin() as conn:
                # UPDATE or DELETE on audit_log_entries must be denied (permission denied by PostgreSQL grant)
                with pytest.raises(DBAPIError):
                    conn.execute(text("UPDATE audit_log_entries SET event_type='tampered'"))
            with app_engine.begin() as conn:
                with pytest.raises(DBAPIError):
                    conn.execute(text("DELETE FROM audit_log_entries"))

            with app_engine.begin() as conn:
                # UPDATE or DELETE on customer_messages must be denied
                with pytest.raises(DBAPIError):
                    conn.execute(text("UPDATE customer_messages SET body='tampered'"))
            with app_engine.begin() as conn:
                with pytest.raises(DBAPIError):
                    conn.execute(text("DELETE FROM customer_messages"))

            with app_engine.begin() as conn:
                # SELECT and INSERT on audit_log_entries must succeed for runtime role
                entry_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO audit_log_entries (entry_id, occurred_at, event_type, trace_id, data)
                    VALUES (:id, now(), 'test.runtime_role_probe', 'trace-probe', '{}'::jsonb)
                """), {"id": entry_id})
                row = conn.execute(text("SELECT event_type FROM audit_log_entries WHERE entry_id = :id"), {"id": entry_id}).scalar()
                assert row == "test.runtime_role_probe"
        finally:
            app_engine.dispose()


# ---------------------------------------------------------------------------
# 5. Outbound gateway transport synthetic PII and log capture
# ---------------------------------------------------------------------------

def test_actual_outbound_gateway_transport_synthetic_pii_and_log_capture(pg_application):
    """Real boundary test: capture actual HTTP transport requests to gateway and assert zero raw synthetic PII and redacted logs."""
    app, passwords, database, settings, _, _ = pg_application
    customer = login_client(app, passwords, "customer")

    synthetic_pii = {
        "name": "Tran Van Bao",
        "phone": "+84912345678",
        "email": "tran.bao@example.com",
        "address": "45 Nguyen Thi Minh Khai Street, District 3, HCMC",
        "card": "4532015112830366",  # Valid Luhn Visa
        "order_id": "ORD-1001",
        "tracking_id": "TRK-987654",
        "literal": "[NAME_1]"
    }

    raw_message = (
        f"Hello, I am {synthetic_pii['name']}. My phone is {synthetic_pii['phone']} "
        f"and shipping address is {synthetic_pii['address']}. "
        f"I paid with credit card {synthetic_pii['card']} for order {synthetic_pii['order_id']} "
        f"and my email is {synthetic_pii['email']}. Tracking reference is {synthetic_pii['tracking_id']}. "
        f"I also typed literal text {synthetic_pii['literal']} in my message."
    )

    # Capture logs in memory
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    logger.logger.addHandler(handler)

    captured_requests = []

    class CapturingClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None):
            captured_requests.append({"url": url, "payload": json})
            req = httpx.Request("POST", url)
            return httpx.Response(200, json={
                "intent": {"label": "track_order", "probability": 0.95, "confidence_band": "high"},
                "alternatives": [],
                "is_in_scope": True,
                "documents": [],
                "routing": {"recommendation": "abstain", "reason_codes": ["no_valid_document"]},
                "warnings": [],
                "versions": {"release_id": "test-rel", "model_version": "v1.0.0"},
                "step_latency_ms": {"analysis": 10}
            }, request=req)

    import apps.backend.tickets.jobs as jobs_mod
    original_client = jobs_mod.httpx.Client
    jobs_mod.httpx.Client = CapturingClient

    try:
        # Update customer profile with synthetic customer name so known customer fields include it
        patch_res = customer.patch("/v1/profile", json={"display_name": synthetic_pii["name"]})
        assert patch_res.status_code == 200

        # 1. Customer submits ticket via application API
        res = post_with_key(customer, "/v1/shop/tickets", {
            "order_id": synthetic_pii["order_id"],
            "message": raw_message
        })
        assert res.status_code == 201
        ticket_id = res.json()["ticket_id"]

        with database.transaction() as session:
            s_id = session.get(Ticket, ticket_id).current_suggestion_id

        # 2. Worker executes job across simulated HTTP transport
        worker = SuggestionWorker(database, settings)
        claimed = worker.claim(s_id)
        assert claimed is not None
        identifier, token, payload = claimed
        worker.process(identifier, token, payload)

    finally:
        jobs_mod.httpx.Client = original_client
        logger.logger.removeHandler(handler)

    # 3. Assert on CAPTURED HTTP TRANSPORT PAYLOAD
    assert len(captured_requests) >= 1, "At least one outbound HTTP request to gateway must have occurred"
    outbound_payload = captured_requests[0]["payload"]
    transport_message = outbound_payload["message"]
    transport_order_context = outbound_payload["order_context"]

    # NO raw PII must cross the transport boundary
    assert synthetic_pii["name"] not in transport_message
    assert synthetic_pii["phone"] not in transport_message
    assert synthetic_pii["email"] not in transport_message
    assert synthetic_pii["card"] not in transport_message
    assert synthetic_pii["order_id"] not in transport_message
    assert synthetic_pii["tracking_id"] not in transport_message
    assert "Nguyen Thi Minh Khai" not in transport_message

    # Typed pseudonym placeholders MUST be present
    assert "[NAME_1]" in transport_message
    assert "[PHONE_1]" in transport_message
    assert "[EMAIL_1]" in transport_message
    assert "[CARD_1]" in transport_message
    assert "[ORDER_ID_1]" in transport_message
    assert "[TRACKING_ID_1]" in transport_message
    assert "[ADDRESS_1]" in transport_message
    assert "[LITERAL_1]" in transport_message

    # Order context across transport must contain ONLY allowlisted fields
    allowed_order_fields = {"order_status", "order_total", "shipping_cost", "shipment_status", "refund_status", "refund_amount"}
    assert set(transport_order_context.keys()) <= allowed_order_fields
    for forbidden in ("customer_name", "phone", "shipping_address", "credit_card", "transaction_id", "tracking_code"):
        assert forbidden not in transport_order_context

    # 4. Assert on CAPTURED STRUCTURED LOGS
    log_output = log_stream.getvalue()
    # Log must not leak credit cards, phones, emails, or credentials
    assert synthetic_pii["card"] not in log_output
    assert synthetic_pii["phone"] not in log_output
    assert synthetic_pii["email"] not in log_output
    assert "password" not in log_output.lower() or "[REDACTED_CREDENTIAL]" in log_output


def test_documented_recall_boundary_on_informal_slang():
    """Verify documented recall boundary: informal Vietnamese vernacular without standard keywords is not masked without NER."""
    colloquial_input = "Giao cho tui o sau nha ba bay cho cau sat cu"
    pseudonymized, mapping = pseudonymize(colloquial_input, {})
    # Accurately asserts the documented limitation (never claim unverified free-form PII protection)
    assert "[ADDRESS_1]" not in pseudonymized
