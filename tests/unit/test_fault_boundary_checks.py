"""Unit tests for Task C offline/synthetic fault-boundary verification (`0` live requests)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.fault_boundary_runner import (
    COMPANION_FAULT_CASE_IDS,
    PRIMARY_TARGET_CASE_IDS,
    SpyLLMClient,
    ZeroBudgetTransport,
    _classify_fault_outcome,
    _run_pipeline_runner_case,
    load_acceptance_fault_cases,
)
from pipeline.evaluation.live_provider_verification import BudgetExhaustedBeforeNetworkError

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_CASES = REPO_ROOT / "data" / "benchmarks" / "system" / "v2" / "acceptance" / "cases.jsonl"


def test_zero_budget_transport_blocks_gemini_before_network() -> None:
    guard = ZeroBudgetTransport()
    assert guard.max_requests == 0
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent")
    with pytest.raises(BudgetExhaustedBeforeNetworkError):
        guard.handle_request(req)
    assert guard.requests_attempted == 1
    assert guard.rejected_before_network_count == 1


def test_acceptance_v2_fault_cases_preserve_frozen_primary_and_companion_ids() -> None:
    rows = load_acceptance_fault_cases(ACCEPTANCE_CASES)
    ids = {r["id"]: r for r in rows}
    assert set(PRIMARY_TARGET_CASE_IDS) <= set(ids.keys())
    assert set(COMPANION_FAULT_CASE_IDS) <= set(ids.keys())
    assert ids["unc-track_order-03"]["expected"]["must_escalate"] is True
    assert ids["unc-return_policy-04"]["expected"]["must_escalate"] is True
    assert ids["unc-track_order-05"]["expected"]["must_escalate"] is True


def test_classify_fault_outcome_distinguishes_strict_pass_from_safe_fallback_mismatch() -> None:
    case = {
        "id": "unc-track_order-03",
        "fault": "ml_timeout",
        "text": "Where is my package ORD-1001?",
        "expected": {
            "actions": ["escalate", "clarify", "manual_fallback"],
            "reason_any": ["ml_timeout"],
            "must_escalate": True,
            "must_not_draft": True,
            "team": "order_support",
        },
    }
    strict = _classify_fault_outcome(
        case=case,
        surface="test",
        scenario="strict",
        raw_action="escalate",
        mapped_action="escalate",
        reason_codes=["ml_timeout"],
        no_draft_preserved=True,
        llm_calls=0,
    )
    assert strict["verdict"] == "STRICT_PASS"

    fallback = _classify_fault_outcome(
        case=case,
        surface="test",
        scenario="fallback",
        raw_action="manual_fallback",
        mapped_action="manual_fallback",
        reason_codes=["ml_unavailable"],
        no_draft_preserved=True,
        llm_calls=0,
    )
    assert fallback["verdict"] == "SAFE_FALLBACK_MISMATCH"
    assert fallback["checks"]["no_draft_ok"] is True
    assert fallback["checks"]["strict_must_escalate_matched"] is False
    assert fallback["checks"]["reason_any_matched"] is False


def test_pipeline_runner_unit_faults_zero_llm_calls(tmp_path: Path) -> None:
    rows = {r["id"]: r for r in load_acceptance_fault_cases(ACCEPTANCE_CASES)}
    release = json.loads((REPO_ROOT / "apps" / "ai_service" / "kb-release.json").read_text(encoding="utf-8"))
    allowed = {(d["document_id"], str(d["version"])) for d in release["documents"]}
    commerce = CommerceAdapter(data_path=str(REPO_ROOT / "data" / "knowledge" / "mock_orders.json"))
    retrieval = RetrievalAdapter(
        kb_path=str(REPO_ROOT / "data" / "knowledge" / "approved_kb.v2.json"),
        allowed_document_versions=allowed,
    )
    spy_llm = SpyLLMClient(mode="forbid", configured=True)

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    timeout_client = IntentClient(
        base_url="http://ml.local",
        http_client=httpx.Client(transport=httpx.MockTransport(timeout_handler), trust_env=False),
    )
    r_timeout = _run_pipeline_runner_case(
        case=rows["unc-track_order-03"],
        scenario="unit_ml_timeout",
        intent_client=timeout_client,
        commerce=commerce,
        retrieval=retrieval,
        spy_llm=spy_llm,
        store_dir=tmp_path,
    )
    assert r_timeout["observed"]["raw_action"] == "manual_fallback"
    assert set(r_timeout["observed"]["reason_codes"]) == {"ml_unavailable", "ml_timeout"}
    assert r_timeout["observed"]["no_draft_preserved"] is True
    assert r_timeout["checks"]["no_draft_ok"] is True
    assert r_timeout["observed"]["llm_calls"] == 0
    assert r_timeout["verdict"] == "SAFE_FALLBACK_MISMATCH"

    # Commerce unauthorized when intent resolves to track_order
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "intent": "track_order",
                "confidence": 0.96,
                "margin": 0.85,
                "top_k": [{"intent": "track_order", "probability": 0.96}],
                "model_version": "unit-v1",
                "verified": True,
            },
        )

    ok_client = IntentClient(
        base_url="http://ml.local",
        expected_model_version="unit-v1",
        http_client=httpx.Client(transport=httpx.MockTransport(ok_handler), trust_env=False),
    )
    r_comm = _run_pipeline_runner_case(
        case=rows["unc-track_order-05"],
        scenario="unit_commerce_unauthorized",
        intent_client=ok_client,
        commerce=commerce,
        retrieval=retrieval,
        spy_llm=spy_llm,
        store_dir=tmp_path,
    )
    assert r_comm["observed"]["raw_action"] == "escalate"
    assert "commerce_unauthorized_customer" in r_comm["observed"]["reason_codes"]
    assert r_comm["observed"]["no_draft_preserved"] is True
    assert r_comm["checks"]["no_draft_ok"] is True
    assert r_comm["observed"]["llm_calls"] == 0
    assert r_comm["verdict"] == "SAFE_FALLBACK_MISMATCH"
