"""Focused Stage A typed fault propagation & privacy boundary tests (offline, zero live calls)."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import logging
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Suggestion, Ticket
from apps.backend.seed import seed
from apps.backend.tickets.jobs import AI_REASONS, SuggestionWorker, validate_analysis
from apps.backend.tickets.service import allowed_actions, require_ticket
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.mock_dependencies import MockPolicyEncoder


def _make_isolated_backend_app(tmp_path):
    db_path = tmp_path / "synthetic_supportiq.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    database = Database(engine)
    database.create_schema()
    passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
    seed(database, passwords)
    settings = Settings(
        database_url_app=f"sqlite:///{db_path}",
        database_url_owner=f"sqlite:///{db_path}",
        allowed_origins=["http://testserver"],
        session_cookie_secure=False,
        ai_service_base_url="http://mock-ai-service:8002",
        # Explicit offline opt-out for unit transport-fault tests without spaCy en_core_web_sm
        require_privacy_ner=False,
    )
    app = create_app(settings=settings, database=database, start_worker=False)
    return app, passwords, database, settings, engine


def _login(app, passwords, role="customer", name=None):
    client = TestClient(app, headers={"Origin": "http://testserver"})
    resp = client.post("/v1/sessions", json={"login_name": name or f"{role}-1", "password": passwords[role]})
    assert resp.status_code == 201, resp.text
    return client


def _create_ticket_and_claim(customer, database, settings, message="What is the return policy?", order_id="ORD-1001"):
    resp = customer.post(
        "/v1/shop/tickets",
        json={"order_id": order_id, "message": message},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert resp.status_code == 201, resp.text
    ticket_id = resp.json()["ticket_id"]
    with database.transaction() as session:
        s_id = session.get(Ticket, ticket_id).current_suggestion_id
    worker = SuggestionWorker(database, settings)
    claimed = worker.claim(s_id)
    assert claimed is not None
    return ticket_id, worker, claimed


class _FailingQueryEncoder:
    def encode_passages(self, texts):
        vecs = np.ones((len(texts), 384), dtype=np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs

    def encode_queries(self, texts):
        raise RuntimeError("secret_db_dsn=postgres://svc:TOP_SECRET_PW@db.internal/supportiq")


def test_retrieval_adapter_encoder_unavailable_bounded_no_raw_error(monkeypatch):
    def _boom_encoder():
        raise RuntimeError("hf_token=SECRET_TOKEN_XYZ_123 failed download")

    monkeypatch.setattr("apps.core_backend.retrieval.adapter.PolicyEncoder", _boom_encoder)
    adapter = RetrievalAdapter(kb_path="data/knowledge/approved_kb.v2.json")
    res = adapter.retrieve("What is the return window?", "return_policy")
    assert res["status"] == "encoder_unavailable"
    assert res["evidence"] == []
    assert "encoder_unavailable" in res.get("reason_codes", [])
    assert "error" not in res
    assert "SECRET_TOKEN_XYZ_123" not in json.dumps(res)


def test_retrieval_adapter_runtime_encoder_failure_preserves_bounded_codes_without_raw_exception(caplog):
    release = json.loads(open("apps/ai_service/kb-release.json", encoding="utf-8").read())
    allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
    adapter = RetrievalAdapter(
        kb_path="data/knowledge/approved_kb.v2.json",
        encoder=_FailingQueryEncoder(),
        allowed_document_versions=allowed,
    )
    with caplog.at_level(logging.WARNING):
        res = adapter.retrieve("What is the return window?", "return_policy")

    assert res["status"] == "encoder_failure"
    assert res["evidence"] == []
    assert "encoder_failure" in res.get("reason_codes", [])
    assert "encoder_failed" in res.get("reason_codes", [])
    serialized = json.dumps(res) + "\n" + caplog.text
    assert "TOP_SECRET_PW" not in serialized
    assert "secret_db_dsn" not in serialized


def test_retrieval_adapter_missing_evidence_remains_distinct_from_encoder_faults():
    release = json.loads(open("apps/ai_service/kb-release.json", encoding="utf-8").read())
    allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
    adapter = RetrievalAdapter(
        kb_path="data/knowledge/approved_kb.v2.json",
        encoder=MockPolicyEncoder(),
        allowed_document_versions=allowed,
        relevance_threshold=0.99,
    )
    res_low = adapter.retrieve("completely unrelated microwave query", "return_policy", current_time=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert res_low["status"] == "no_evidence"
    assert "below_relevance_threshold" in res_low.get("reason_codes", [])
    assert "encoder_failure" not in res_low.get("reason_codes", [])
    assert "encoder_unavailable" not in res_low.get("reason_codes", [])

    res_exp = adapter.retrieve("What is return policy?", "return_policy", current_time=datetime(2028, 6, 1, tzinfo=timezone.utc))
    assert res_exp["status"] == "no_match"


@pytest.mark.parametrize("endpoint", ["/v1/analyses", "/v1/drafts"])
def test_ai_service_endpoint_distinguishes_ml_timeout_ml_error_and_unavailable_without_secrets(monkeypatch, endpoint):
    from apps.ai_service import main

    state = {"ready": True, "exc": None}

    class _FakeModel:
        model_checksum = "weights"
        verified_model_version = "v1.0.0"
        model_mode = "trained"
        verified = True

        def load(self):
            return None

        def is_ready(self):
            return state["ready"]

        def predict(self, text):
            if state["exc"] is not None:
                raise state["exc"]
            return {"intent": "return_policy", "confidence": 0.95, "margin": 0.8}

    monkeypatch.setattr("apps.ml_inference.app.ModelContainer", lambda: _FakeModel())
    monkeypatch.setattr(
        "apps.core_backend.retrieval.adapter.RetrievalAdapter",
        lambda **kwargs: SimpleNamespace(
            index=object(),
            eligible_versions=[],
            relevance_threshold=0.55,
            retrieve=lambda *a, **kw: {"status": "success", "evidence": [], "has_conflict": False},
        ),
    )
    monkeypatch.setattr(
        main,
        "AiSettings",
        lambda: SimpleNamespace(
            supportiq_enable_llm=False,
            gemini_api_key=SecretStr(""),
            gemini_model="gemini-3.5-flash-lite",
        ),
    )

    body = {"message": "What is the return policy?", "as_of": "2026-06-01T00:00:00Z", "order_context": {}}
    with TestClient(main.create_app(), raise_server_exceptions=False) as client:
        # 1. ML unavailable (not ready)
        state["ready"] = False
        r_unavail = client.post(endpoint, json=body)
        assert r_unavail.status_code == 503
        assert r_unavail.headers.get("X-SupportIQ-Error-Code") == "ml_unavailable"

        # 2. ML TimeoutError -> 504 ml_timeout (NEVER 500 or raw secret)
        state["ready"] = True
        state["exc"] = TimeoutError("ML_SECRET_DEADLINE_TOKEN=999")
        r_timeout = client.post(endpoint, json=body)
        assert r_timeout.status_code == 504
        assert r_timeout.headers.get("X-SupportIQ-Error-Code") == "ml_timeout"
        assert "ml_timeout" in json.dumps(r_timeout.json())
        assert "ML_SECRET_DEADLINE_TOKEN" not in r_timeout.text

        # 3. ML RuntimeError -> 503 ml_error (NEVER raw secret)
        state["exc"] = RuntimeError("ML_SECRET_STACK_DETAIL=pw")
        r_err = client.post(endpoint, json=body)
        assert r_err.status_code == 503
        assert r_err.headers.get("X-SupportIQ-Error-Code") == "ml_error"
        assert "ml_error" in json.dumps(r_err.json())
        assert "ML_SECRET_STACK_DETAIL" not in r_err.text

        # 4. Unexpected non-ValueError/RuntimeError exception -> still bounded 503 ml_error
        state["exc"] = ZeroDivisionError("UNEXPECTED_INTERNAL_SECRET")
        r_unexp = client.post(endpoint, json=body)
        assert r_unexp.status_code == 503
        assert r_unexp.headers.get("X-SupportIQ-Error-Code") == "ml_error"
        assert "UNEXPECTED_INTERNAL_SECRET" not in r_unexp.text


def test_jobs_ai_reasons_accepts_typed_fault_codes_and_rejects_unbounded():
    for code in ("ml_timeout", "ml_error", "ml_unavailable", "encoder_unavailable", "encoder_failure", "encoder_failed", "ai_service_unavailable"):
        assert code in AI_REASONS
        payload = {
            "intent": {"label": "return_policy", "probability": 0.9, "confidence_band": "high"},
            "alternatives": [],
            "documents": [],
            "warnings": [],
            "routing": {"recommendation": "escalate", "reason_codes": ["insufficient_evidence", code]},
            "versions": {"release_id": "rel-1"},
        }
        assert validate_analysis(payload)["routing"]["reason_codes"] == ["insufficient_evidence", code]

    bad = {
        "intent": {"label": "return_policy", "probability": 0.9, "confidence_band": "high"},
        "alternatives": [],
        "documents": [],
        "warnings": [],
        "routing": {"recommendation": "escalate", "reason_codes": ["raw exception secret string"]},
        "versions": {"release_id": "rel-1"},
    }
    with pytest.raises(ValueError, match="Invalid routing"):
        validate_analysis(bad)


def test_jobs_worker_propagates_typed_faults_with_compatibility_on_synthetic_db(tmp_path):
    app, passwords, database, settings, engine = _make_isolated_backend_app(tmp_path)
    try:
        customer = _login(app, passwords, "customer")
        staff = _login(app, passwords, "staff")

        scenarios = [
            ("timeout_exc", lambda url: (_ for _ in ()).throw(httpx.ReadTimeout("timeout_secret=abc")), "ml_timeout", "unavailable", ["ml_timeout", "ai_service_unavailable"]),
            ("http_504", lambda url: httpx.Response(504, json={"detail": {"error_code": "ml_timeout", "reason_codes": ["ml_timeout", "ai_service_unavailable"]}}, headers={"X-SupportIQ-Error-Code": "ml_timeout"}, request=httpx.Request("POST", url)), "ml_timeout", "unavailable", ["ml_timeout", "ai_service_unavailable"]),
            ("http_503_ml_error", lambda url: httpx.Response(503, json={"detail": {"error_code": "ml_error", "reason_codes": ["ml_error", "ai_service_unavailable"]}}, headers={"X-SupportIQ-Error-Code": "ml_error"}, request=httpx.Request("POST", url)), "ml_error", "unavailable", ["ml_error", "ai_service_unavailable"]),
            ("http_503_ml_unavail", lambda url: httpx.Response(503, json={"detail": {"error_code": "ml_unavailable", "reason_codes": ["ml_unavailable", "ai_service_unavailable"]}}, headers={"X-SupportIQ-Error-Code": "ml_unavailable"}, request=httpx.Request("POST", url)), "ml_unavailable", "unavailable", ["ml_unavailable", "ai_service_unavailable"]),
            ("connect_err", lambda url: (_ for _ in ()).throw(httpx.ConnectError("secret_creds=pw123")), "ai_service_unavailable", "unavailable", ["ai_service_unavailable"]),
        ]

        import apps.backend.tickets.jobs as jobs_mod
        original_client = jobs_mod.httpx.Client

        for _, handler, expected_fc, expected_status, expected_codes in scenarios:
            ticket_id, worker, (ident, token, payload) = _create_ticket_and_claim(customer, database, settings)

            class _MockClient:
                def __init__(self, *a, **kw):
                    pass
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    pass
                def post(self, url, json=None):
                    return handler(url)

            jobs_mod.httpx.Client = _MockClient
            try:
                worker.process(ident, token, payload)
            finally:
                jobs_mod.httpx.Client = original_client

            ws = staff.get(f"/v1/console/tickets/{ticket_id}").json()
            sugg = ws["suggestion"]
            assert sugg["draft_status"] == expected_status
            assert sugg["failure_code"] == expected_fc
            for code in expected_codes:
                assert code in sugg["reason_codes"]
            assert "timeout_secret" not in json.dumps(sugg)
            assert "secret_creds" not in json.dumps(sugg)
            assert "retry_suggestion" in ws["allowed_actions"]
            assert "send_reply" in ws["allowed_actions"]

        # Encoder failure analysis from ai_service propagates cleanly without AI_REASONS rejection
        ticket_id, worker, (ident, token, payload) = _create_ticket_and_claim(customer, database, settings)

        class _EncoderEscClient:
            def __init__(self, *a, **kw):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def post(self, url, json=None):
                return httpx.Response(
                    200,
                    json={
                        "intent": {"label": "return_policy", "probability": 0.94, "confidence_band": "high"},
                        "alternatives": [],
                        "is_in_scope": True,
                        "documents": [],
                        "routing": {
                            "recommendation": "escalate",
                            "reason_codes": ["insufficient_evidence", "encoder_failure", "encoder_failed"],
                        },
                        "warnings": [],
                        "versions": {"release_id": "test-rel"},
                        "step_latency_ms": {"analysis": 4},
                    },
                    request=httpx.Request("POST", url),
                )

        jobs_mod.httpx.Client = _EncoderEscClient
        try:
            worker.process(ident, token, payload)
        finally:
            jobs_mod.httpx.Client = original_client

        ws = staff.get(f"/v1/console/tickets/{ticket_id}").json()
        assert ws["suggestion"]["analysis_status"] == "ready"
        assert ws["suggestion"]["draft_status"] == "escalation_recommended"
        assert "encoder_failure" in ws["suggestion"]["reason_codes"]
        assert "encoder_failed" in ws["suggestion"]["reason_codes"]
    finally:
        engine.dispose()


def test_cross_customer_order_intake_returns_404_with_zero_ticket_creation(tmp_path):
    """Cross-customer order intake intentionally denies with 404 & creates 0 tickets (privacy > frozen escalate expectation)."""
    app, passwords, database, settings, engine = _make_isolated_backend_app(tmp_path)
    try:
        customer = _login(app, passwords, "customer")
        with database.transaction() as session:
            before_tickets = len(session.scalars(select(Ticket)).all())
            before_suggestions = len(session.scalars(select(Suggestion)).all())

        resp = customer.post(
            "/v1/shop/tickets",
            json={"order_id": "ORD-1002", "message": "Where is order ORD-1002?"},
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert resp.status_code == 404
        assert resp.json().get("type") == "urn:supportiq:problem:not-found"

        with database.transaction() as session:
            after_tickets = len(session.scalars(select(Ticket)).all())
            after_suggestions = len(session.scalars(select(Suggestion)).all())
        assert after_tickets == before_tickets
        assert after_suggestions == before_suggestions
    finally:
        engine.dispose()
