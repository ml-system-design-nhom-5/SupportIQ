"""Offline diagnostic & regression tests for plan `c4520c1` verification helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

import apps.ml_inference.app as ml_app
from apps.ai_service.engine import Engine
from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.routing import load_policy_v2
from apps.core_backend.intent.schemas import RoutingContext
from apps.core_backend.llm.gemini import LLMError
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from pipeline.evaluation.guard_corrections_verifier import (
    UnraisedInvalidLLMClient,
    classify_corrected_fault_contract,
    make_mock_gemini_client,
    verify_historic_fault_evidence_unchanged,
)


class _StubRetriever:
    def __init__(self) -> None:
        self.eligible_versions = [
            SimpleNamespace(
                doc_id="POL-RET-001",
                version="2.0",
                metadata=SimpleNamespace(valid_from="2025-01-01", valid_to="2026-12-31"),
            )
        ]

    def retrieve(self, query: str, intent: str, *, role: str = "agent", current_time=None):
        return {
            "status": "success",
            "has_conflict": False,
            "evidence": [
                {
                    "source_type": "policy",
                    "document_id": "POL-RET-001",
                    "doc_id": "POL-RET-001",
                    "version": "2.0",
                    "title": "Return Policy",
                    "excerpt": "Tiki Trading items may be returned within 30 days via free Tiki courier pickup.",
                    "score": 0.91,
                }
            ],
        }


def _make_offline_ml_client(monkeypatch) -> tuple[IntentClient, Any]:
    policy = load_policy_v2()

    class _DummyModel:
        model_version = "v2.0.0"
        verified_model_version = "v2.0.0"
        model_mode = "trained"
        verified = True
        calibration_schema_version = "temp_v1"
        id2label = {i: lbl for i, lbl in enumerate(sorted(policy.all_46_labels))}

        @staticmethod
        def is_ready():
            return True

        @staticmethod
        def is_trained_ready():
            return True

        @staticmethod
        def predict(text: str, temperature=None, calibrated: bool = True):
            return {
                "intent": "return_policy",
                "confidence": 0.94,
                "margin": 0.86,
                "top_k": [{"intent": "return_policy", "probability": 0.94}],
                "score_kind": "calibrated_probability",
                "model_version": "v2.0.0",
                "model_mode": "trained",
                "verified": True,
                "raw_confidence": 0.95,
                "raw_margin": 0.88,
                "raw_score_kind": "uncalibrated_softmax",
                "calibration_temperature": 1.1,
                "selective_accepted": True,
                "rejected_by_experimental_adapter": False,
                "rejector_decision": "accept",
            }

    dummy = _DummyModel()
    monkeypatch.setattr(ml_app, "container", dummy)
    tc = TestClient(ml_app.app)

    def bridge(req: httpx.Request) -> httpx.Response:
        resp = tc.post(req.url.path, content=req.content, headers=dict(req.headers))
        return httpx.Response(status_code=resp.status_code, content=resp.content, headers=dict(resp.headers))

    client = IntentClient(
        base_url="http://ml-service",
        expected_model_version="v2.0.0",
        http_client=httpx.Client(transport=httpx.MockTransport(bridge), trust_env=False),
    )
    return client, dummy


def test_historic_fault_boundary_hashes_remain_immutable() -> None:
    status = verify_historic_fault_evidence_unchanged()
    assert status["all_matched"] is True
    for entry in status["files"].values():
        assert entry["exists"] is True
        assert entry["matched"] is True


def test_real_gemini_client_accepts_valid_grounded_and_rejects_invalid_citations(tmp_path: Path, monkeypatch) -> None:
    intent_client, dummy_model = _make_offline_ml_client(monkeypatch)
    retriever = _StubRetriever()
    policy = load_policy_v2()
    ai_policy = policy.model_dump()

    gemini_valid, urls = make_mock_gemini_client("valid_grounded")
    gemini_bad, _ = make_mock_gemini_client("invalid_unknown_citation")
    gemini_uncited, _ = make_mock_gemini_client("invalid_uncited")
    try:
        runner = PipelineRunner(
            intent_client=intent_client,
            policy=policy,
            commerce_adapter=CommerceAdapter(),
            retrieval_adapter=retriever,
            store=PersistentStore(str(tmp_path / "store.sqlite3")),
            llm_client=gemini_valid,
            clock=lambda: datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        )
        res = runner.run(
            "What is the return window for Tiki Trading items?",
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                as_of="2026-06-15T10:00:00+00:00",
            ),
            run_id="valid-gemini",
        )
        assert res["action"] == "retrieve_draft"
        assert res["llm_called"] is True
        assert "[S1]" in res["draft_body"]
        assert res["confidence"] == 0.94
        assert res["margin"] == 0.86
        assert res["score_kind"] == "calibrated_probability"
        assert len(urls) == 1

        engine = Engine(dummy_model, retriever, gemini_valid, {"release_id": "offline"}, ai_policy)
        eng_out = engine.draft(
            {
                "message": "What is the return window for Tiki Trading items?",
                "order_context": {},
                "as_of": "2026-06-15T10:00:00Z",
            }
        )
        assert eng_out["status"] == "draft_ready"
        assert eng_out["draft"]["citations"]

        ev = [{"source_type": "policy", "document_id": "POL-RET-001", "version": "2.0", "excerpt": "30 days."}]
        with pytest.raises(LLMError) as exc1:
            gemini_bad.generate("Return window?", "return_policy", ev)
        assert exc1.value.code == "llm_invalid_citations"

        with pytest.raises(LLMError) as exc2:
            gemini_uncited.generate("Return window?", "return_policy", ev)
        assert exc2.value.code == "llm_invalid_citations"
    finally:
        gemini_valid.close()
        gemini_bad.close()
        gemini_uncited.close()
        intent_client.close()


def test_engine_rejects_unraised_invalid_injected_outputs() -> None:
    policy = load_policy_v2().model_dump()
    retriever = _StubRetriever()

    class _MockModel:
        @staticmethod
        def predict(msg: str):
            return {"intent": "return_policy", "confidence": 0.95, "margin": 0.85, "top_k": []}

    for mode, expected_code in (
        ("unknown_citation", "grounding_failed"),
        ("uncited_long_claim", "grounding_failed"),
        ("placeholder_leak", "llm_invalid_output"),
    ):
        eng = Engine(_MockModel(), retriever, UnraisedInvalidLLMClient(mode), {"release_id": "offline"}, policy)
        out = eng.draft({"message": "What is the return window?", "order_context": {}, "as_of": "2026-06-15T10:00:00Z"})
        assert out["status"] == "llm_unavailable"
        assert expected_code in out["reason_codes"]
        assert "draft" not in out


def test_classify_corrected_fault_contract_preserves_privacy_404_distinction() -> None:
    privacy_rec = {
        "case_id": "unc-track_order-05",
        "fault": "commerce_unauthorized",
        "surface": "backend_pg_gateway",
        "scenario": "backend_pg_explicit_unauthorized_order",
        "verdict": "INTAKE_DENIAL_404_MISMATCH",
        "expected": {
            "actions": ["escalate", "manual_fallback"],
            "reason_any": ["commerce_unauthorized"],
            "must_escalate": True,
            "must_not_draft": True,
        },
        "observed": {
            "http_status": 404,
            "raw_action": "http_404_denied",
            "mapped_action": "http_404_denied",
            "reason_codes": [],
            "no_draft_preserved": True,
            "llm_calls": 0,
            "is_authority_required": None,
        },
        "details": {"ticket_count_after_submit": 0},
    }
    summary = classify_corrected_fault_contract(privacy_rec)
    assert summary["privacy_intake_404_preserved"] is True
    assert summary["strict_must_escalate_matched"] is False
    assert summary["no_draft_preserved"] is True
    assert "privacy requirement" in (summary["boundary_note"] or "")

    fallback_rec = {
        "case_id": "unc-track_order-03",
        "fault": "ml_timeout",
        "surface": "backend_pg_gateway",
        "scenario": "backend_pg_analysis_read_timeout",
        "verdict": "SAFE_FALLBACK_MISMATCH",
        "expected": {
            "actions": ["escalate", "manual_fallback"],
            "reason_any": ["ml_timeout"],
            "must_escalate": True,
            "must_not_draft": True,
        },
        "observed": {
            "http_status": 201,
            "raw_action": "unavailable",
            "mapped_action": "manual_fallback",
            "reason_codes": ["ml_timeout"],
            "no_draft_preserved": True,
            "llm_calls": 0,
            "is_authority_required": False,
        },
        "details": {"allowed_actions": ["submit_reply_proposal", "escalate", "send_reply"]},
    }
    fb_summary = classify_corrected_fault_contract(fallback_rec)
    assert fb_summary["safe_fallback_or_expected_action_matched"] is True
    assert fb_summary["strict_reason_any_matched"] is True
    assert fb_summary["strict_must_escalate_matched"] is False
    assert fb_summary["allowed_actions"] == ["submit_reply_proposal", "escalate", "send_reply"]
