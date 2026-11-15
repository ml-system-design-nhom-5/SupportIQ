"""Gap 3 (Privacy / NER fail-closed & literal collision hardening) TDD suite."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import AuditEntry, Suggestion, SuggestionJob, Ticket
from apps.backend.seed import seed
from apps.backend.tickets.jobs import AI_REASONS, SuggestionWorker
from apps.backend.tickets.privacy import (
    PLACEHOLDER,
    is_privacy_ner_available,
    pseudonymize,
    restore,
    validate_egress_payload,
)
from apps.backend.tickets.service import act, allowed_actions


def _make_pg_app(**setting_overrides):
    import json

    secrets_path = Path(os.environ.get("SUPPORTIQ_APPLICATION_SECRETS", ".local/application.json"))
    if not secrets_path.exists():
        secrets_path = Path(__file__).resolve().parents[2] / ".local/application.json"
    local = json.loads(secrets_path.read_text())
    owner_url = local["database_url_owner"]
    schema = "test_gap3_" + uuid.uuid4().hex
    root = create_engine(owner_url)
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(owner_url, connect_args={"options": f"-csearch_path={schema}"})
    database = Database(engine)
    database.create_schema()
    passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
    seed(database, passwords)
    cfg = {
        "database_url_app": local.get("database_url_app", owner_url),
        "database_url_owner": owner_url,
        "allowed_origins": ["http://testserver"],
        "session_cookie_secure": False,
        "ai_service_base_url": "http://unknown-ai-egress:8002",
    }
    cfg.update(setting_overrides)
    settings = Settings(**cfg)
    app = create_app(settings=settings, database=database, start_worker=False)
    return root, schema, engine, database, settings, passwords, app


def _cleanup_pg(root, schema, engine):
    engine.dispose()
    with root.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    root.dispose()


def _login(app, passwords, role: str) -> TestClient:
    client = TestClient(app, headers={"Origin": "http://testserver"})
    resp = client.post("/v1/sessions", json={"login_name": f"{role}-1", "password": passwords[role]})
    assert resp.status_code == 201, resp.text
    return client


def _post(client: TestClient, path: str, body: dict):
    return client.post(path, json=body, headers={"Idempotency-Key": str(uuid.uuid4())})


def test_gap3_settings_and_pseudonymize_default_strict():
    """Settings and pseudonymize() must default strict (no implicit opt-out when spaCy is absent)."""
    s = Settings(
        _env_file=None,
        database_url_app="sqlite:///:memory:",
        ai_service_base_url="http://external-ai:8002",
    )
    assert s.require_privacy_ner is True
    assert is_privacy_ner_available() is False
    with pytest.raises(ValueError):
        pseudonymize("Yesterday Johnathan Smith asked about order ORD-1001.", {})


def test_gap3_strict_default_blocks_egress_when_ner_missing_and_disables_retry(monkeypatch):
    """Missing spaCy/en_core_web_sm fails closed -> pseudonymization_failed, 0 jobs, 0 HTTP calls, retry disabled."""
    from apps.backend.tickets import jobs as jobs_mod

    monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: None)

    def _boom_client(*args, **kwargs):
        raise AssertionError("No external httpx.Client call may occur when privacy fails")

    monkeypatch.setattr(jobs_mod.httpx, "Client", _boom_client)

    root, schema, engine, database, settings, passwords, app = _make_pg_app()
    try:
        assert settings.require_privacy_ner is True
        customer = _login(app, passwords, "customer")
        staff = _login(app, passwords, "staff")

        raw_msg = "Hello, I am Johnathan Smith living in Ho Chi Minh City calling about ORD-1001."
        created = _post(customer, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": raw_msg})
        assert created.status_code == 201, created.text
        ticket_id = created.json()["ticket_id"]

        ws = staff.get(f"/v1/console/tickets/{ticket_id}")
        assert ws.status_code == 200
        body = ws.json()
        assert body["suggestion"]["analysis_status"] == "unavailable"
        assert body["suggestion"]["draft_status"] == "unavailable"
        assert body["suggestion"]["reason_codes"] == ["pseudonymization_failed"]
        assert "retry_suggestion" not in body["allowed_actions"]
        assert "send_reply" in body["allowed_actions"]

        retry = _post(staff, f"/v1/console/tickets/{ticket_id}/suggestions", {})
        assert retry.status_code == 422

        with database.transaction() as session:
            jobs = session.scalars(select(SuggestionJob)).all()
            assert jobs == []
            sug = session.get(Suggestion, session.get(Ticket, ticket_id).current_suggestion_id)
            assert sug.request_payload["message"] == ""
            assert "Johnathan Smith" not in str(sug.request_payload)
            assert "Ho Chi Minh City" not in str(sug.request_payload)
            priv_audits = [
                a for a in session.scalars(select(AuditEntry)).all()
                if a.event_type == "message.pseudonymized" and a.ticket_id == ticket_id
            ]
            assert len(priv_audits) == 1
            assert priv_audits[0].data["outcome"] == "failed"

        sent = _post(staff, f"/v1/console/tickets/{ticket_id}/replies", {
            "basis": "no_ai_draft",
            "body": "Handled manually after privacy guard.",
        })
        assert sent.status_code == 201
    finally:
        _cleanup_pg(root, schema, engine)


@pytest.mark.parametrize("mode", ["load_raises", "infer_raises"])
def test_gap3_ner_exceptions_fail_closed_and_retain_sticky_authority(monkeypatch, mode: str):
    """NER load/runtime exceptions fail closed, block retry, and keep sticky Gap 2 authority."""
    if mode == "load_raises":
        def _bad_loader():
            raise RuntimeError("broken spacy wheel / model path /user/secret")
        monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", _bad_loader)
    else:
        def _bad_nlp(text: str):
            raise RuntimeError(f"spacy crashed on: {text}")
        monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: _bad_nlp)

    root, schema, engine, database, settings, passwords, app = _make_pg_app()
    try:
        customer = _login(app, passwords, "customer")
        staff = _login(app, passwords, "staff")
        manager = _login(app, passwords, "manager")

        msg = "My lawyer Johnathan Smith insists you grant an exception for ORD-1001."
        created = _post(customer, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": msg})
        assert created.status_code == 201
        tid = created.json()["ticket_id"]

        ws = staff.get(f"/v1/console/tickets/{tid}").json()
        assert ws["is_authority_required"] is True
        assert ws["suggestion"]["reason_codes"] == ["pseudonymization_failed"]
        assert "retry_suggestion" not in ws["allowed_actions"]
        assert "send_reply" not in ws["allowed_actions"]

        assert _post(staff, f"/v1/console/tickets/{tid}/replies", {
            "basis": "no_ai_draft",
            "body": "Unauthorized direct reply.",
        }).status_code == 403

        prop = _post(staff, f"/v1/console/tickets/{tid}/reply-proposals", {
            "basis": "no_ai_draft",
            "body": "Prepared for manager sign-off.",
        })
        assert prop.status_code == 201
        assert _post(manager, f"/v1/console/tickets/{tid}/replies", {
            "basis": "reply_proposal",
            "proposal_id": prop.json()["proposal_id"],
            "body": "Prepared for manager sign-off.",
        }).status_code == 201
    finally:
        _cleanup_pg(root, schema, engine)


def test_gap3_worker_pre_dispatch_gate_blocks_unmasked_or_missing_ner_zero_egress(monkeypatch):
    """SuggestionWorker.process blocks before any _post_ai call if strict NER unavailable or payload unmasked."""
    monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: None)
    root, schema, engine, database, settings_offline, passwords, app_off = _make_pg_app(require_privacy_ner=False)
    try:
        customer = _login(app_off, passwords, "customer")
        tid = _post(customer, "/v1/shop/tickets", {
            "order_id": "ORD-1001",
            "message": "My lawyer wants a refund exception on ORD-1001.",
        }).json()["ticket_id"]

        with database.transaction() as session:
            t = session.get(Ticket, tid)
            t.is_authority_required = True
            sug = session.get(Suggestion, t.current_suggestion_id)
            job = session.get(SuggestionJob, sug.suggestion_id)
            job.lease_token = "tok-worker-1"
            sid = sug.suggestion_id

        calls: list[tuple[str, dict]] = []
        strict_settings = Settings(
            _env_file=None,
            database_url_app=settings_offline.database_url_app,
            ai_service_base_url="http://external-ai:8002",
            require_privacy_ner=True,
        )
        worker = SuggestionWorker(database, strict_settings)
        monkeypatch.setattr(worker, "_post_ai", lambda ep, payload, b: calls.append((ep, payload)) or {})

        worker.process(sid, "tok-worker-1", {"message": "Where is [ORDER_ID_1]?", "order_context": {}, "as_of": "2026-11-15T00:00:00Z"})
        assert calls == []

        with database.transaction() as session:
            sug = session.get(Suggestion, sid)
            assert sug.payload["analysis_status"] == "unavailable"
            assert sug.payload["draft_status"] == "unavailable"
            assert "pseudonymization_failed" in sug.payload["reason_codes"]
            assert session.get(Ticket, tid).is_authority_required is True

        # Also validate raw unmasked PII payload rejected even when require_ner=False
        with pytest.raises(ValueError):
            validate_egress_payload({"message": "Contact leak@example.com directly"}, require_ner=False)
        with pytest.raises(ValueError):
            validate_egress_payload({"message": ""}, require_ner=False)
        with pytest.raises(ValueError):
            validate_egress_payload({"message": "Card 4532-0151-1283-0366 unmasked"}, require_ner=False)
        with pytest.raises(ValueError):
            validate_egress_payload({"message": "Order ORD-1001 unmasked"}, require_ner=False)
    finally:
        _cleanup_pg(root, schema, engine)


def test_gap3_valid_spacy_ner_masks_synthetic_pii_and_restores_locally_only(monkeypatch):
    """When valid spaCy NER is available under strict default, free-form PII is masked before AI egress and restored only locally."""
    class _Ent:
        def __init__(self, label, text):
            self.label_ = label
            self.text = text

    class _Doc:
        def __init__(self, ents):
            self.ents = ents

    def fake_nlp(text: str):
        ents = []
        if "Johnathan Smith" in text:
            ents.append(_Ent("PERSON", "Johnathan Smith"))
        if "Da Nang" in text:
            ents.append(_Ent("GPE", "Da Nang"))
        return _Doc(ents)

    monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: fake_nlp)

    captured_egress: list[dict] = []

    def handler(request: httpx.Request):
        import json as _json

        payload = _json.loads(request.content.decode("utf-8"))
        captured_egress.append(payload)
        analysis = {
            "intent": {"label": "track_order", "probability": 0.94, "confidence_band": "high"},
            "alternatives": [],
            "documents": [],
            "warnings": [],
            "routing": {"recommendation": "draft", "reason_codes": []},
            "versions": {"release_id": "rel-gap3"},
        }
        if request.url.path == "/v1/analyses":
            return httpx.Response(200, json=analysis)
        return httpx.Response(200, json={
            "status": "draft_ready",
            "reason_codes": [],
            "analysis": analysis,
            "draft": {
                "segments": [{
                    "segment_id": "s-1",
                    "paragraph_index": 0,
                    "text": "Hello [NAME_1], shipping to [ADDRESS_1] for [ORDER_ID_1].",
                    "citation_ids": [],
                }],
                "citations": [],
            },
        })

    root, schema, engine, database, settings, passwords, app = _make_pg_app()
    try:
        assert settings.require_privacy_ner is True
        customer = _login(app, passwords, "customer")
        staff = _login(app, passwords, "staff")

        created = _post(customer, "/v1/shop/tickets", {
            "order_id": "ORD-1001",
            "message": "Friend Johnathan Smith in Da Nang asked about ORD-1001.",
        })
        assert created.status_code == 201
        tid = created.json()["ticket_id"]

        with database.transaction() as session:
            sid = session.get(Ticket, tid).current_suggestion_id

        with httpx.Client(transport=httpx.MockTransport(handler)) as fake_http:
            worker = SuggestionWorker(database, settings, http_client=fake_http)
            claimed = worker.claim(sid)
            assert claimed is not None
            worker.process(*claimed)

        assert len(captured_egress) == 2
        for req_body in captured_egress:
            assert "Johnathan Smith" not in req_body["message"]
            assert "Da Nang" not in req_body["message"]
            assert "ORD-1001" not in req_body["message"]
            assert "[NAME_1]" in req_body["message"]
            assert "[ADDRESS_1]" in req_body["message"]
            assert "[ORDER_ID_1]" in req_body["message"]

        # Shop view has NO suggestion/mapping leak; console view restores locally for staff
        shop_res = customer.get(f"/v1/shop/tickets/{tid}").json()
        assert "suggestion" not in shop_res
        ws = staff.get(f"/v1/console/tickets/{tid}").json()
        assert "Johnathan Smith" in ws["suggestion"]["draft"]["text"]
        assert "Da Nang" in ws["suggestion"]["draft"]["text"]
    finally:
        _cleanup_pg(root, schema, engine)


def test_gap3_literal_placeholder_nul_unlimited_index_and_overlap_hardening():
    """Verify collision-free placeholder escaping, NUL markers, >999 IDs, overlaps, unicode, and limits."""
    # 1. Customer literal [EMAIL_1], [LITERAL_1], [[EMAIL_1]], \x000\x00 + real email + known local-part
    raw = (
        "Hi alice, email alice@example.com vs fake [EMAIL_1] [LITERAL_1] "
        "nested [[EMAIL_1]] nul \x000\x00 idx [EMAIL_1000]"
    )
    known = {"NAME": ["alice"], "EMAIL": ["alice@example.com"]}
    masked, mapping = pseudonymize(raw, known, require_ner=False)

    assert "alice@example.com" not in masked
    assert "[EMAIL_1]" in masked
    assert "[NAME_1]@example.com" not in masked
    assert "\x000\x00" in masked  # Customer NUL marker untouched, not forged to [LITERAL_1]
    assert restore(masked, mapping) == raw

    # Customer fake [EMAIL_1] became a LITERAL, never restoring into real alice@example.com!
    simulated_llm_echo = "You wrote [LITERAL_1] and real [EMAIL_1] and [LITERAL_2] and [LITERAL_3]"
    restored_reply = restore(simulated_llm_echo, mapping)
    assert restored_reply == "You wrote [EMAIL_1] and real alice@example.com and [LITERAL_1] and [EMAIL_1000]"

    # 2. Exceeding 999 identifiers must NOT hit {0,2} regex truncation bug
    many = " ".join(f"u{i}@ex.co" for i in range(1, 200))
    mt, mm = pseudonymize(many, {}, require_ner=False)
    assert "[EMAIL_199]" in mt
    assert restore(mt, mm) == many
    assert PLACEHOLDER.fullmatch("[EMAIL_1234]") is not None
    assert PLACEHOLDER.fullmatch("[LITERAL_10005]") is not None
    assert restore("Val [EMAIL_1234] and [LITERAL_10005]", {
        "[EMAIL_1234]": "x@y.co",
        "[LITERAL_10005]": "[EMAIL_1]",
    }) == "Val x@y.co and [EMAIL_1]"

    # 3. Overlapping known entries: longer ADDRESS beats shorter NAME inside address
    overlap_raw = "Deliver to 123 Le Loi Street, An Phu for An"
    om, omap = pseudonymize(overlap_raw, {"NAME": ["An"], "ADDRESS": ["123 Le Loi Street, An Phu"]}, require_ner=False)
    assert om == "Deliver to [ADDRESS_1] for [NAME_1]"
    assert restore(om, omap) == overlap_raw

    # 4. Unicode + length bounds preserved
    uni = "Xin chào Nguyễn Văn Bình tại Đà Nẵng 😀 email binh@example.vn"
    um, umap = pseudonymize(uni, {"NAME": ["Nguyễn Văn Bình"]}, require_ner=False)
    assert "binh@example.vn" not in um
    assert "Nguyễn Văn Bình" not in um
    assert restore(um, umap) == uni

    assert pseudonymize("a" * 4000, {}, require_ner=False)[0] == "a" * 4000
    with pytest.raises(ValueError):
        pseudonymize("", {}, require_ner=False)
    with pytest.raises(ValueError):
        pseudonymize("a" * 4001, {}, require_ner=False)


def test_gap3_reason_codes_bounded_29_and_no_pii_in_logs(caplog, monkeypatch):
    """AI_REASONS remains 29 bounded remote codes and structured logs never emit raw customer PII or mappings."""
    assert len(AI_REASONS) == 29
    monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: None)

    with caplog.at_level(logging.INFO):
        with pytest.raises(ValueError):
            pseudonymize("Secret customer Johnathan Smith card 4532015112830366", {})

    assert "Johnathan Smith" not in caplog.text
    assert "4532015112830366" not in caplog.text
