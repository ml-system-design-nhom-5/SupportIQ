"""End-to-end API, worker, concurrency, and reason-contract tests for Safety Gap 2 (authority & outage closure)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from apps.ai_service.engine import Engine
from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database, utcnow
from apps.backend.platform.models import Account, AuditEntry, CustomerMessage, Suggestion, SuggestionJob, Ticket
from apps.backend.seed import seed
from apps.backend.tickets.jobs import AI_REASONS, SuggestionWorker, validate_analysis
from apps.core_backend.safety import has_authority_request
from tests.unit.test_safety_slice1_gap1_a import StaticIntentModel, StaticScopeRetriever, StubLLM, _load_real_kb_and_release


def _pg_secrets() -> dict:
    secrets_path = Path(os.environ.get("SUPPORTIQ_APPLICATION_SECRETS", ".local/application.json"))
    if not secrets_path.exists():
        fallback = Path("F:/Năm 3/SD/project/SupportIQ/.local/application.json")
        if fallback.exists():
            secrets_path = fallback
        else:
            pytest.skip("PostgreSQL credentials not found in .local/application.json")
    return json.loads(secrets_path.read_text(encoding="utf-8"))


def _make_pg_app(ai_service_base_url: str | None = None, require_privacy_ner: bool = True):
    local = _pg_secrets()
    owner_url = local["database_url_owner"]
    schema = "test_gap2_" + uuid.uuid4().hex
    root = create_engine(owner_url)
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
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
        ai_service_base_url=ai_service_base_url,
        require_privacy_ner=require_privacy_ner,
    )
    app = create_app(settings=settings, database=database, start_worker=False)
    return root, schema, engine, database, settings, passwords, app


@pytest.fixture(scope="module")
def pg_app_ai_down():
    """Disposable PG app simulating complete AI outage (ai_service_base_url=None)."""
    root, schema, engine, database, settings, passwords, app = _make_pg_app(ai_service_base_url=None)
    try:
        yield app, passwords, database, settings
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


@pytest.fixture(scope="module")
def pg_app_ai_enabled():
    """Disposable PG app with AI URL configured (worker invoked explicitly with mock HTTP; offline NER opt-out)."""
    root, schema, engine, database, settings, passwords, app = _make_pg_app(
        ai_service_base_url="http://mock-ai-service:8002",
        require_privacy_ner=False,
    )
    try:
        yield app, passwords, database, settings
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def _login(app, passwords, role: str, login_name: str | None = None) -> TestClient:
    client = TestClient(app, headers={"Origin": "http://testserver"})
    res = client.post("/v1/sessions", json={"login_name": login_name or f"{role}-1", "password": passwords[role]})
    assert res.status_code == 201, res.text
    return client


def _post(client: TestClient, path: str, body: dict, key: str | None = None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def _claim_job(database: Database, settings: Settings, ticket_id: str) -> tuple[str, str, dict]:
    worker = SuggestionWorker(database, settings)
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        sug = session.get(Suggestion, t.current_suggestion_id)
        job = session.get(SuggestionJob, sug.suggestion_id)
        job.lease_token = str(uuid.uuid4())
        token = job.lease_token
        ident = sug.suggestion_id
        payload = dict(sug.request_payload)
    return ident, token, payload


@pytest.mark.parametrize(
    "message",
    [
        "Could you make an exception for my return window on ORD-1001?",
        "I will have my lawyer contact your legal team if not resolved.",
        "Please grant an exception for order ORD-1001.",
        "I have filed a bank dispute over this transaction.",
        "There are unauthorized charges on my account statement.",
        "Can a supervisor approve a manager exception on this refund?",
        "Transfer me to a human manager right away.",
    ],
)
def test_gap2_authority_requests_lock_staff_even_when_ai_offline(pg_app_ai_down, message: str):
    """Authority signals covered by has_authority_request must lock staff replies during AI outage."""
    app, passwords, database, _ = pg_app_ai_down
    customer = _login(app, passwords, "customer")
    staff = _login(app, passwords, "staff")
    manager = _login(app, passwords, "manager")

    created = _post(customer, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": message})
    assert created.status_code == 201, created.text
    ticket_id = created.json()["ticket_id"]

    ws = staff.get(f"/v1/console/tickets/{ticket_id}")
    assert ws.status_code == 200
    body = ws.json()
    assert body["is_authority_required"] is True
    assert body["suggestion"]["draft_status"] == "unavailable"
    assert "send_reply" not in body["allowed_actions"]
    assert "submit_reply_proposal" in body["allowed_actions"]

    denied = _post(staff, f"/v1/console/tickets/{ticket_id}/replies", {
        "basis": "no_ai_draft",
        "body": "Direct reply without approval.",
    })
    assert denied.status_code == 403
    assert denied.json()["type"] == "urn:supportiq:problem:authority-required"
    with database.transaction() as session:
        assert session.get(Ticket, ticket_id).reply is None

    proposal = _post(staff, f"/v1/console/tickets/{ticket_id}/reply-proposals", {
        "basis": "no_ai_draft",
        "body": "Escalated draft for authority approval.",
    })
    assert proposal.status_code == 201
    prop_id = proposal.json()["proposal_id"]

    approved = _post(manager, f"/v1/console/tickets/{ticket_id}/replies", {
        "basis": "reply_proposal",
        "proposal_id": prop_id,
        "body": "Escalated draft for authority approval.",
    })
    assert approved.status_code == 201


def test_gap2_authority_remains_sticky_under_timeout_bogus_ai_and_pseudonymization_failure(pg_app_ai_enabled, monkeypatch):
    """Pending timeout, bogus AI draft (reason_codes=[]), and pseudonymization failure cannot clear is_authority_required."""
    app, passwords, database, settings = pg_app_ai_enabled
    customer = _login(app, passwords, "customer")
    staff = _login(app, passwords, "staff")
    admin = _login(app, passwords, "admin")

    # 1. Timeout + late bogus 'draft' with no requires_authority
    res = _post(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "My lawyer is reviewing these unauthorized charges on ORD-1001.",
    })
    assert res.status_code == 201
    tid = res.json()["ticket_id"]

    # While pending, send_reply is unavailable and authority flag is already True
    ws_pending = staff.get(f"/v1/console/tickets/{tid}").json()
    assert ws_pending["is_authority_required"] is True
    assert "send_reply" not in ws_pending["allowed_actions"]

    # Worker suffers ML timeout
    import apps.backend.tickets.jobs as jobs_mod
    worker = SuggestionWorker(database, settings)
    ident, token, payload = _claim_job(database, settings, tid)
    orig_client = jobs_mod.httpx.Client

    class _TimeoutClient:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def post(self, url, json=None):
            raise httpx.ReadTimeout("timed out")

    jobs_mod.httpx.Client = _TimeoutClient
    try:
        worker.process(ident, token, payload)
    finally:
        jobs_mod.httpx.Client = orig_client

    ws_after_timeout = staff.get(f"/v1/console/tickets/{tid}").json()
    assert ws_after_timeout["is_authority_required"] is True
    assert ws_after_timeout["suggestion"]["draft_status"] == "unavailable"
    assert _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Attempt"}).status_code == 403

    # Retry + bogus AI service returning draft recommendation with empty reason_codes MUST NOT clear authority
    retry_res = _post(staff, f"/v1/console/tickets/{tid}/suggestions", {})
    assert retry_res.status_code == 202
    ident2, token2, payload2 = _claim_job(database, settings, tid)
    bogus_analysis = {
        "intent": {"label": "track_order", "probability": 0.99, "confidence_band": "high"},
        "alternatives": [],
        "documents": [],
        "routing": {"recommendation": "draft", "reason_codes": []},
        "warnings": [],
        "versions": {"release_id": "rel-bogus"},
        "step_latency_ms": {"analysis": 1},
    }
    worker.store(ident2, token2, "analysis", bogus_analysis, 1)
    assert staff.get(f"/v1/console/tickets/{tid}").json()["is_authority_required"] is True
    assert _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Attempt 2"}).status_code == 403

    # 2. Pseudonymization failure must STILL set is_authority_required=True and block staff reply
    import apps.backend.tickets.service as svc_mod

    def _boom(*a, **kw):
        raise ValueError("ner missing")

    monkeypatch.setattr(svc_mod, "pseudonymize", _boom)
    res_priv = _post(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "Please grant an exception or I will file a bank dispute.",
    })
    monkeypatch.undo()
    assert res_priv.status_code == 201
    priv_tid = res_priv.json()["ticket_id"]
    ws_priv = staff.get(f"/v1/console/tickets/{priv_tid}").json()
    assert ws_priv["is_authority_required"] is True
    assert "pseudonymization_failed" in ws_priv["suggestion"]["reason_codes"]
    assert _post(staff, f"/v1/console/tickets/{priv_tid}/replies", {"basis": "no_ai_draft", "body": "Bypass"}).status_code == 403
    assert _post(admin, f"/v1/console/tickets/{priv_tid}/replies", {"basis": "no_ai_draft", "body": "Admin handled."}).status_code == 201


def test_gap2_role_promotion_cannot_bypass_self_approval_via_direct_reply(pg_app_ai_down):
    """Staff promoted to manager after submitting proposal must NOT approve OR directly send on that ticket."""
    app, passwords, database, _ = pg_app_ai_down
    customer = _login(app, passwords, "customer")
    admin = _login(app, passwords, "admin")

    # Create a dedicated promotable staff account via DB seed pattern
    promotable_pw = uuid.uuid4().hex
    from argon2 import PasswordHasher
    promotable_login = f"staff-promo-{uuid.uuid4().hex[:6]}"
    with database.transaction() as session:
        acct = Account(
            account_id=f"acc-promo-{uuid.uuid4().hex[:8]}",
            login_name=promotable_login,
            display_name="Promoted Staff",
            password_hash=PasswordHasher().hash(promotable_pw),
            role="staff",
            is_active=True,
        )
        session.add(acct)
        session.flush()
        promo_id = acct.account_id

    promo_client = _login(app, {promotable_login: promotable_pw}, promotable_login, login_name=promotable_login)
    created = _post(customer, "/v1/shop/tickets", {
        "order_id": "ORD-1001",
        "message": "There are unauthorized charges; my lawyer will follow up.",
    })
    assert created.status_code == 201
    tid = created.json()["ticket_id"]

    prop = _post(promo_client, f"/v1/console/tickets/{tid}/reply-proposals", {
        "basis": "no_ai_draft",
        "body": "Proposal from staff before promotion.",
    })
    assert prop.status_code == 201
    proposal_id = prop.json()["proposal_id"]

    # Admin promotes staff -> manager; prior session invalidated
    promoted = _post(admin, f"/v1/admin/accounts/{promo_id}/role-changes", {"role": "manager"})
    assert promoted.status_code == 201
    assert promo_client.get(f"/v1/console/tickets/{tid}").status_code == 401

    # Re-login as newly promoted manager
    promo_mgr = _login(app, {promotable_login: promotable_pw}, promotable_login, login_name=promotable_login)
    ws = promo_mgr.get(f"/v1/console/tickets/{tid}").json()
    assert "send_reply" not in ws["allowed_actions"]

    # Both reply_proposal AND direct no_ai_draft MUST be rejected with self-approval-forbidden
    res_prop = _post(promo_mgr, f"/v1/console/tickets/{tid}/replies", {
        "basis": "reply_proposal",
        "proposal_id": proposal_id,
        "body": "Proposal from staff before promotion.",
    })
    assert res_prop.status_code == 403
    assert res_prop.json()["type"] == "urn:supportiq:problem:self-approval-forbidden"

    res_direct = _post(promo_mgr, f"/v1/console/tickets/{tid}/replies", {
        "basis": "no_ai_draft",
        "body": "Trying direct bypass after promotion.",
    })
    assert res_direct.status_code == 403
    assert res_direct.json()["type"] == "urn:supportiq:problem:self-approval-forbidden"

    # Legacy admin CAN still approve another person's proposal
    res_admin = _post(admin, f"/v1/console/tickets/{tid}/replies", {
        "basis": "reply_proposal",
        "proposal_id": proposal_id,
        "body": "Proposal from staff before promotion.",
    })
    assert res_admin.status_code == 201


def test_gap2_concurrent_worker_store_never_downgrades_authority(pg_app_ai_enabled):
    """Concurrent worker stores completion with routine draft cannot downgrade sticky is_authority_required."""
    app, passwords, database, settings = pg_app_ai_enabled
    customer = _login(app, passwords, "customer")

    tids = []
    for idx in range(3):
        res = _post(customer, "/v1/shop/tickets", {
            "order_id": "ORD-1001",
            "message": f"Grant an exception on ORD-1001 case #{idx}.",
        })
        assert res.status_code == 201
        tids.append(res.json()["ticket_id"])

    claims = [_claim_job(database, settings, tid) for tid in tids]
    worker = SuggestionWorker(database, settings)
    routine_analysis = {
        "intent": {"label": "track_order", "probability": 0.95, "confidence_band": "high"},
        "alternatives": [],
        "documents": [{"document_id": "POL-ORD-001", "version": "2.0", "title": "Order", "snippet": "Track order.", "rank": 1, "validity": "valid"}],
        "routing": {"recommendation": "draft", "reason_codes": []},
        "warnings": [],
        "versions": {"release_id": "rel-concurrent"},
        "step_latency_ms": {"analysis": 1},
    }
    routine_draft = {
        "status": "draft_ready",
        "reason_codes": [],
        "analysis": routine_analysis,
        "draft": {"segments": [{"segment_id": "s0", "paragraph_index": 0, "text": "Your order is shipped.", "citation_ids": ["S1"]}],
                  "citations": [{"citation_id": "S1", "source_type": "kb_document", "document_id": "POL-ORD-001", "version": "2.0", "snippet": "Track order."}]},
        "staff_note": "Review.",
        "step_latency_ms": {"llm": 1},
    }

    def _run_store(claim):
        ident, token, _ = claim
        worker.store(ident, token, "analysis", routine_analysis, 1)
        worker.store(ident, token, "draft", routine_draft, 1)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(_run_store, claims))

    with database.transaction() as session:
        for tid in tids:
            t = session.get(Ticket, tid)
            assert t.is_authority_required is True


def test_gap2_controls_normative_authority_cross_customer_idempotency_and_audit(pg_app_ai_down):
    """Preserve normal staff reply, normative has_authority_request semantics, cross-customer 404, idempotency, and audit."""
    app, passwords, database, _ = pg_app_ai_down
    c1 = _login(app, passwords, "customer", login_name="customer-1")
    c2 = _login(app, passwords, "customer", login_name="customer-2")
    staff = _login(app, passwords, "staff")

    # Normal supported case & normative non-authority negations allow staff reply directly
    for msg in (
        "There is no payment dispute; when will order ORD-1001 arrive?",
        "Without needing an exception, how do I request courier pickup?",
    ):
        assert has_authority_request(msg) is False
        r = _post(c1, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": msg})
        assert r.status_code == 201
        tid = r.json()["ticket_id"]
        assert staff.get(f"/v1/console/tickets/{tid}").json()["is_authority_required"] is False
        # Cross-customer access denied (404)
        assert c2.get(f"/v1/shop/tickets/{tid}").status_code == 404
        # Idempotent reply creation succeeds once
        idem_key = str(uuid.uuid4())
        rep1 = _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Handled cleanly."}, key=idem_key)
        rep2 = _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Handled cleanly."}, key=idem_key)
        assert rep1.status_code == 201
        assert rep2.status_code == 201
        assert rep1.json()["reply_id"] == rep2.json()["reply_id"]

    # Quoted / benign lawyer mention follows existing normative has_authority_request behavior (True -> locked)
    quoted_lawyer = "A friend jokingly mentioned a lawyer in a movie, when does ORD-1001 arrive?"
    assert has_authority_request(quoted_lawyer) is True
    ql_tid = _post(c1, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": quoted_lawyer}).json()["ticket_id"]
    assert _post(staff, f"/v1/console/tickets/{ql_tid}/replies", {"basis": "no_ai_draft", "body": "Blocked"}).status_code == 403

    with database.transaction() as session:
        event_types = {e.event_type for e in session.scalars(select(AuditEntry)).all()}
        assert "ticket.created" in event_types
        assert "reply.sent" in event_types


def test_gap2_reason_codes_contract_exact_bounded_set():
    """Engine-emitted reason codes match jobs.AI_REASONS while arbitrary unknown strings fail closed."""
    _, _, policy = _load_real_kb_and_release()
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002"], "track_order": ["POL-ORD-001"]})
    eng = Engine(StaticIntentModel("return_product"), retriever, StubLLM(), {"release_id": "gap2-rel"}, policy=policy)

    for probe in (
        "My lawyer will review this unauthorized charge.",
        "Can I return this at a physical store?",
        "Transfer me to a human agent.",
    ):
        analysis = eng.analyse({"message": probe, "as_of": "2026-06-15T10:00:00Z"})
        assert set(analysis["routing"]["reason_codes"]) <= AI_REASONS
        assert validate_analysis(analysis) is analysis

    for valid_code in ("requires_authority", "insufficient_evidence", "no_valid_document", "ml_timeout", "encoder_failure"):
        assert valid_code in AI_REASONS

    with pytest.raises(ValueError, match="Invalid routing"):
        validate_analysis({
            "intent": {"label": "return_product", "probability": 0.9, "confidence_band": "high"},
            "alternatives": [],
            "documents": [],
            "warnings": [],
            "routing": {"recommendation": "escalate", "reason_codes": ["unregistered_reason_code"]},
            "versions": {"release_id": "gap2-rel"},
        })
