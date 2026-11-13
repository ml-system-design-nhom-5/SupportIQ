"""RED->GREEN safety & parity tests for complete HTTP IntentClient -> decide_route -> PipelineRunner path."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import apps.ml_inference.app as ml_app
from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.routing import load_policy_v2
from apps.core_backend.intent.schemas import RoutingContext
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore


class SpyCompliantLLM:
    """No-network spy LLM that succeeds normally if reached so routing bugs are never masked."""

    def __init__(self):
        self.configured = True
        self.calls: list[dict[str, Any]] = []

    def generate(self, query: str, intent: str, evidence: list[dict[str, Any]], business_context: Any = None) -> dict[str, Any]:
        self.calls.append({"query": query, "intent": intent, "evidence_count": len(evidence)})
        return {
            "body": f"Grounded reply for {intent} [S1].",
            "citations": ["S1"],
            "answerable": True,
            "is_clarification": False,
        }


class StubRetriever:
    def __init__(self, evidence: list[dict[str, Any]] | None = None, *, has_conflict: bool = False):
        self.eligible_versions = [
            SimpleNamespace(
                doc_id="POL-RET-001",
                version="1",
                metadata=SimpleNamespace(valid_from="2026-01-01", valid_to="2026-12-31"),
            )
        ]
        self._evidence = (
            [
                {
                    "document_id": "POL-RET-001",
                    "doc_id": "POL-RET-001",
                    "version": "1",
                    "title": "Return Policy",
                    "excerpt": "Tiki Trading items may be returned within 30 days via free Tiki courier pickup.",
                    "score": 0.88,
                }
            ]
            if evidence is None
            else evidence
        )
        self._has_conflict = has_conflict

    def retrieve(self, query: str, intent: str, *, role: str = "agent", current_time=None) -> dict[str, Any]:
        return {
            "status": "success" if self._evidence else "no_match",
            "evidence": list(self._evidence),
            "has_conflict": self._has_conflict,
        }


def _make_runner(
    tmp_path: Path,
    monkeypatch,
    pred_map: dict[str, dict[str, Any]],
    *,
    retriever: Any = None,
    policy_approved: bool = True,
) -> tuple[PipelineRunner, SpyCompliantLLM, PersistentStore, IntentClient]:
    policy = load_policy_v2()
    if not policy_approved:
        policy = policy.model_copy(update={"approved": False})

    class DummyContainer:
        model_version = "v2.0.0"
        verified_model_version = "v2.0.0"
        model_mode = "trained"
        verified = True
        calibration_schema_version = "temp_v1"
        id2label = {i: label for i, label in enumerate(sorted(policy.all_46_labels))}

        @staticmethod
        def is_ready():
            return True

        @staticmethod
        def is_trained_ready():
            return True

        @staticmethod
        def predict(text: str, temperature=None, calibrated: bool = True):
            return dict(
                pred_map.get(
                    text,
                    {
                        "intent": "return_policy",
                        "confidence": 0.93,
                        "margin": 0.82,
                        "top_k": [{"intent": "return_policy", "probability": 0.93}],
                        "score_kind": "calibrated_probability",
                        "model_version": "v2.0.0",
                        "model_mode": "trained",
                        "verified": True,
                        "raw_confidence": 0.94,
                        "raw_margin": 0.84,
                        "raw_score_kind": "uncalibrated_softmax",
                        "calibration_temperature": 1.1,
                        "selective_accepted": True,
                        "rejected_by_experimental_adapter": False,
                        "rejector_decision": "accept",
                    },
                )
            )

    monkeypatch.setattr(ml_app, "container", DummyContainer())
    tc = TestClient(ml_app.app)

    def _asgi_bridge(req: httpx.Request) -> httpx.Response:
        resp = tc.post(req.url.path, content=req.content, headers=dict(req.headers))
        return httpx.Response(status_code=resp.status_code, content=resp.content, headers=dict(resp.headers))

    client = IntentClient(
        base_url="http://ml-service",
        expected_model_version="v2.0.0",
        http_client=httpx.Client(transport=httpx.MockTransport(_asgi_bridge)),
    )
    spy_llm = SpyCompliantLLM()
    store = PersistentStore(str(tmp_path / "pipeline_runs.sqlite3"))
    runner = PipelineRunner(
        intent_client=client,
        policy=policy,
        commerce_adapter=CommerceAdapter(),
        retrieval_adapter=retriever or StubRetriever(),
        store=store,
        llm_client=spy_llm,
        clock=lambda: datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    return runner, spy_llm, store, client


def _ctx(**kwargs) -> RoutingContext:
    defaults = {
        "ticket_customer_id": "cust_1",
        "caller_customer_id": "cust_1",
        "verified_scope": "ticket:read order:read",
        "as_of": "2026-06-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return RoutingContext(**defaults)


@pytest.mark.parametrize(
    "query,expected_terminal",
    [
        ("How do I schedule a postal pickup for returning my parcel?", "escalate"),
        ("What is your return policy and can I also close my account?", "escalate"),
        ("How do I file my income tax return?", "manual_fallback"),
    ],
)
def test_pipeline_runner_blocks_outside_scope_and_ood_even_when_intent_stage_recommends_draft(
    tmp_path: Path, monkeypatch, query: str, expected_terminal: str
):
    runner, spy_llm, _, client = _make_runner(tmp_path, monkeypatch, {})
    try:
        res = runner.run(query, _ctx(), run_id=f"run-{expected_terminal}")
        assert res["initial_routing_action"] == "retrieve_draft"
        assert res["action"] == expected_terminal
        assert res["llm_called"] is False
        assert spy_llm.calls == []
    finally:
        client.close()


@pytest.mark.parametrize(
    "scope_gap_query",
    [
        "What are the customs import duty charges for shipping internationally?",
        "What was the return policy window during the old 2023 promotional year?",
        "Can I use the expired legacy refund exception timeline from 2022?",
        "Explain the draft unratified shipping compensation guideline.",
        "Show me the confidential staff manual for overriding payment limits.",
        "Which rule applies if one section says 30 days and another section says 14 days?",
    ],
)
def test_pipeline_runner_escalates_policy_scope_gaps_before_generation(
    tmp_path: Path, monkeypatch, scope_gap_query: str
):
    runner, spy_llm, _, client = _make_runner(tmp_path, monkeypatch, {})
    try:
        res = runner.run(scope_gap_query, _ctx(), run_id="run-scope-gap")
        assert res["initial_routing_action"] == "retrieve_draft"
        assert res["action"] == "escalate"
        assert "insufficient_evidence" in res["reason_codes"]
        assert res["llm_called"] is False
        assert spy_llm.calls == []
    finally:
        client.close()


def test_pipeline_runner_blocks_retriever_has_conflict_and_cross_border_gaps(tmp_path: Path, monkeypatch):
    runner_conflict, spy_conflict, _, c1 = _make_runner(tmp_path / "c", monkeypatch, {}, retriever=StubRetriever(has_conflict=True))
    try:
        res_c = runner_conflict.run("What is the standard return window?", _ctx(), run_id="run-conflict")
        assert res_c["action"] == "escalate"
        assert "conflicting_sources" in res_c["reason_codes"]
        assert "insufficient_evidence" in res_c["reason_codes"]
        assert spy_conflict.calls == []
    finally:
        c1.close()

    runner_cb, spy_cb, _, c2 = _make_runner(tmp_path / "cb", monkeypatch, {})
    try:
        res_cb = runner_cb.run("How much is overseas international shipping?", _ctx(), run_id="run-cb")
        assert res_cb["action"] == "manual_fallback"
        assert "no_valid_document" in res_cb["reason_codes"]
        assert spy_cb.calls == []
    finally:
        c2.close()


def test_pipeline_runner_escalates_explicit_authority_and_human_phrases_even_with_valid_order(tmp_path: Path, monkeypatch):
    runner, spy_llm, _, client = _make_runner(tmp_path, monkeypatch, {})
    try:
        res_auth = runner.run(
            "I want a fraud policy exception for this unauthorized transaction!",
            _ctx(
                ticket_customer_id="demo-customer",
                caller_customer_id="demo-customer",
                extracted_slots={"order_id": "ORD-1001"},
                is_personal_lookup=True,
            ),
            run_id="run-auth",
        )
        assert res_auth["action"] == "escalate"
        assert "requires_authority" in res_auth["reason_codes"]
        assert res_auth["target_queue"] == "manager"
        assert spy_llm.calls == []

        res_unauth = runner.run(
            "Where is my order ORD-1001?",
            _ctx(
                ticket_customer_id="cust_other",
                caller_customer_id="cust_other",
                extracted_slots={"order_id": "ORD-1001"},
                is_personal_lookup=True,
            ),
            run_id="run-unauth-commerce",
        )
        assert res_unauth["action"] == "escalate"
        assert "commerce_unauthorized_customer" in res_unauth["reason_codes"]
        assert spy_llm.calls == []

        res_human = runner.run("Transfer me to a live customer support representative.", _ctx(), run_id="run-human")
        assert res_human["action"] == "escalate"
        assert "human_agent_requested" in res_human["reason_codes"]
        assert res_human["requested_team"] == "general_support"
        assert spy_llm.calls == []
    finally:
        client.close()


def test_pipeline_runner_preserves_clean_supported_drafts_overrides_slots_commerce_and_approval(tmp_path: Path, monkeypatch):
    rejected_pred = {
        "intent": "return_policy",
        "confidence": 0.45,
        "margin": 0.05,
        "top_k": [{"intent": "return_policy", "probability": 0.45}],
        "score_kind": "calibrated_probability",
        "model_version": "v2.0.0",
        "model_mode": "trained",
        "verified": True,
        "raw_confidence": 0.45,
        "raw_margin": 0.05,
        "raw_score_kind": "uncalibrated_softmax",
        "calibration_temperature": 1.1,
        "selective_accepted": False,
        "rejected_by_experimental_adapter": True,
        "rejector_decision": "reject",
    }
    runner, spy_llm, _, client = _make_runner(tmp_path / "ok", monkeypatch, {"Rejected but valid override": rejected_pred})
    try:
        # Clean supported query incl. Tiki courier pickup & four-digit currency price must still draft
        res_clean = runner.run(
            "How do I arrange a free Tiki courier pickup for a 2024 VND item?",
            _ctx(),
            run_id="run-clean",
        )
        assert res_clean["action"] == "retrieve_draft"
        assert res_clean["llm_called"] is True
        assert res_clean["must_human_approve"] is True
        assert res_clean["can_execute_transaction"] is False
        assert len(spy_llm.calls) == 1

        # Validated staff override allows clean inquiry to draft
        res_ovr = runner.run(
            "Rejected but valid override",
            _ctx(
                verified_scope="ticket:read intent:override",
                intent_override="return_policy",
                override_provenance={"actor_id": "sup_1", "reason": "confirmed return policy question"},
            ),
            run_id="run-ovr-clean",
        )
        assert res_ovr["action"] == "retrieve_draft"
        assert len(spy_llm.calls) == 2

        # Validated staff override CANNOT bypass policy scope / authority guard
        res_ovr_unsafe = runner.run(
            "Explain the unratified proposed executive return policy.",
            _ctx(
                verified_scope="ticket:read intent:override",
                intent_override="return_policy",
                override_provenance={"actor_id": "sup_1", "reason": "manual check"},
            ),
            run_id="run-ovr-unsafe",
        )
        assert res_ovr_unsafe["action"] == "escalate"
        assert "insufficient_evidence" in res_ovr_unsafe["reason_codes"]
        assert len(spy_llm.calls) == 2
    finally:
        client.close()

    # Policy approval fail-closed preserved
    runner_unapp, spy_unapp, _, c2 = _make_runner(tmp_path / "unapp", monkeypatch, {}, policy_approved=False)
    try:
        res_unapp = runner_unapp.run("What is your standard return window?", _ctx(), run_id="run-unapp")
        assert res_unapp["action"] == "manual_fallback"
        assert "policy_not_approved" in res_unapp["reason_codes"]
        assert spy_unapp.calls == []
    finally:
        c2.close()


def test_pipeline_runner_blocks_clarify_and_abstention_bypass_for_human_fraud_and_tax(tmp_path: Path, monkeypatch):
    low_conf_track = {
        "intent": "track_order",
        "confidence": 0.25,
        "margin": 0.04,
        "top_k": [{"intent": "track_order", "probability": 0.25}, {"intent": "return_policy", "probability": 0.21}],
        "score_kind": "uncalibrated_softmax",
        "model_version": "v2.0.0",
        "model_mode": "trained",
        "verified": True,
    }
    low_conf_ret = {**low_conf_track, "intent": "return_policy"}
    rejected_pred = {
        **low_conf_ret,
        "selective_accepted": False,
        "rejected_by_experimental_adapter": True,
        "rejector_decision": "reject",
    }
    q_human_fraud = "Where is my order? Actually this is fraud and I want a human agent!"
    q_tax = "How do I file my income tax return for this order?"
    q_human_only = "Where is my order? I want to talk to a human agent."
    q_rejected_fraud = "This is fraud, connect me to a human agent!"
    q_unauth_fraud = "Where is ORD-1002? This is fraud and I want a human agent!"

    runner, spy_llm, store, client = _make_runner(
        tmp_path,
        monkeypatch,
        {
            q_human_fraud: low_conf_track,
            q_tax: low_conf_ret,
            q_human_only: low_conf_track,
            q_rejected_fraud: rejected_pred,
            q_unauth_fraud: {**low_conf_track, "confidence": 0.94, "margin": 0.60},
        },
    )
    try:
        r_hf = runner.run(q_human_fraud, _ctx(is_personal_lookup=True), run_id="clarify-hf")
        assert r_hf["initial_routing_action"] == "clarify"
        assert r_hf["action"] == "escalate"
        assert "human_agent_requested" in r_hf["reason_codes"]
        assert "requires_authority" in r_hf["reason_codes"]
        assert r_hf["target_queue"] == "manager"

        r_tax = runner.run(q_tax, _ctx(is_personal_lookup=True), run_id="clarify-tax")
        assert r_tax["initial_routing_action"] == "clarify"
        assert r_tax["action"] == "manual_fallback"
        assert "out_of_scope_intent" in r_tax["reason_codes"]

        r_ho = runner.run(q_human_only, _ctx(is_personal_lookup=True), run_id="clarify-ho")
        assert r_ho["initial_routing_action"] == "clarify"
        assert r_ho["action"] == "escalate"
        assert "human_agent_requested" in r_ho["reason_codes"]

        r_rej = runner.run(q_rejected_fraud, _ctx(), run_id="reject-hf")
        assert r_rej["initial_routing_action"] == "manual_fallback"
        assert r_rej["action"] == "escalate"
        assert "requires_authority" in r_rej["reason_codes"]
        assert "human_agent_requested" in r_rej["reason_codes"]
        assert r_rej["target_queue"] == "manager"

        r_ua = runner.run(
            q_unauth_fraud,
            _ctx(
                ticket_customer_id="cust_other",
                caller_customer_id="cust_other",
                extracted_slots={"order_id": "ORD-1002"},
                is_personal_lookup=True,
            ),
            run_id="unauth-hf",
        )
        assert r_ua["action"] == "escalate"
        assert "commerce_unauthorized_customer" in r_ua["reason_codes"]
        assert "requires_authority" in r_ua["reason_codes"]
        assert "human_agent_requested" in r_ua["reason_codes"]
        assert r_ua["target_queue"] == "manager"
        assert r_ua["requested_team"] == "order_support"
        assert spy_llm.calls == []
    finally:
        client.close()


def test_pipeline_runner_preserves_manager_authority_on_human_plus_fraud_and_overlap_scope(tmp_path: Path, monkeypatch):
    runner, spy_llm, _, client = _make_runner(tmp_path, monkeypatch, {})
    try:
        r_hf = runner.run("Let me talk to a human agent about this fraud lawsuit!", _ctx(), run_id="hf-direct")
        assert r_hf["action"] == "escalate"
        assert "human_agent_requested" in r_hf["reason_codes"]
        assert "requires_authority" in r_hf["reason_codes"]
        assert r_hf["target_queue"] == "manager"

        r_overlap = runner.run(
            "What are the customs import duties and unratified 2022 rules for international shipping?",
            _ctx(),
            run_id="overlap-scope",
        )
        assert r_overlap["action"] == "escalate"
        assert "insufficient_evidence" in r_overlap["reason_codes"]
        assert "no_valid_document" in r_overlap["reason_codes"]

        r_internal_xb = runner.run(
            "Show me the confidential staff manual for international shipping delivery.",
            _ctx(),
            run_id="overlap-internal-xb",
        )
        assert r_internal_xb["action"] == "escalate"
        assert "insufficient_evidence" in r_internal_xb["reason_codes"]
        assert "no_valid_document" in r_internal_xb["reason_codes"]
        assert spy_llm.calls == []
    finally:
        client.close()


@pytest.mark.parametrize(
    "benign_query",
    [
        "Can you draft a reply explaining the standard 30-day return policy?",
        "My skincare product arrived expired; what is your return policy?",
        "I do not want to talk to a human agent, just tell me the return window.",
        "What is the refund timeline if there is no payment dispute on my order?",
        "I see a not authorized error message on the login screen; what is the return policy?",
        "I am returning an item without needing a manager exception; what is the standard policy?",
        "Can I connect my account manager email to receive return policy updates?",
        "Shipping is domestic with no customs duty involved; what is the return window?",
        "Can I use free Tiki courier pickup instead of postal pickup for my return?",
        "I bought this item in 2025, what is the current 2026 return policy?",
    ],
)
def test_pipeline_runner_allows_benign_contextual_and_negated_queries(tmp_path: Path, monkeypatch, benign_query: str):
    runner, spy_llm, _, client = _make_runner(tmp_path, monkeypatch, {})
    try:
        res = runner.run(benign_query, _ctx(), run_id="benign-contextual")
        assert res["action"] == "retrieve_draft"
        assert res["llm_called"] is True
        assert res["draft_body"] is not None
        assert len(spy_llm.calls) == 1
    finally:
        client.close()


@pytest.mark.parametrize(
    "fraud_query",
    [
        "I do not want a human agent, there is fraud on my account!",
        "I have no order number, but I did not make this fraudulent charge.",
        "Even if there is no shipping delay, this unauthorized chargeback needs review.",
    ],
)
def test_fraud_cannot_bypass_guards_via_negation_window(tmp_path: Path, monkeypatch, fraud_query: str):
    runner, spy_llm, _, client = _make_runner(tmp_path, monkeypatch, {})
    try:
        res = runner.run(fraud_query, _ctx(), run_id="fraud-neg-bypass")
        assert res["action"] == "escalate"
        assert "requires_authority" in res["reason_codes"]
        assert res["target_queue"] == "manager"
        assert res["llm_called"] is False
        assert spy_llm.calls == []
    finally:
        client.close()


def test_pipeline_runner_post_generation_validation_and_default_client_contract(tmp_path: Path, monkeypatch):
    import httpx
    import json
    from apps.core_backend.llm.gemini import GeminiDraftClient

    # 1. Valid real GeminiDraftClient output (preserves inline [S1]) must pass cleanly & retain score immutability
    def ok_handler(req):
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-3.5-flash-lite",
                "usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 25},
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "answerable": True,
                                            "answer": "Items may be returned within 30 days. [S1]\n\nThank you for contacting support.",
                                            "citations": ["S1"],
                                            "is_clarification": False,
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ],
            },
        )

    transport = httpx.Client(transport=httpx.MockTransport(ok_handler))
    gemini_ok = GeminiDraftClient(api_key="test-key", model="gemini-3.5-flash-lite", http_client=transport)
    runner_ok, _, store_ok, c_ok = _make_runner(tmp_path / "gok", monkeypatch, {})
    runner_ok.llm_client = gemini_ok
    try:
        res_ok = runner_ok.run("What is your standard return window?", _ctx(), run_id="postgen-ok")
        assert res_ok["action"] == "retrieve_draft"
        assert "[S1]" in res_ok["draft_body"]
        assert res_ok["draft_kind"] == "llm"
        assert res_ok["confidence"] == pytest.approx(0.93)
        assert res_ok["margin"] == pytest.approx(0.82)
        assert res_ok["score_kind"] == "calibrated_probability"
        saved_ok = store_ok.get_run("postgen-ok")
        assert saved_ok is not None and "[S1]" in saved_ok["draft_body"]
        assert res_ok["llm"]["provider"] == "google_ai_studio"
    finally:
        transport.close()
        c_ok.close()

    # 2. Malicious / invalid injected LLM client outputs must fail closed with no stored draft
    bad_payloads = [
        ("uncited_commitment", {"body": "Refunds take 14 business days and cost $50.", "citations": []}),
        ("unknown_citation", {"body": "Return within 30 days. [S9]", "citations": [{"source_id": "S9", "document_id": "POL", "version": "1.0"}]}),
        ("mismatched_doc_citation", {"body": "Return within 30 days. [S1]", "citations": [{"source_id": "S1", "document_id": "FAKE-DOC", "version": "9.9"}]}),
        ("forged_snapshot", {"body": "Return within 30 days. [S1]", "citations": ["S1"], "input_snapshot": {"sources": [{"source_id": "S1", "document_id": "FAKE-DOC", "version": "9.9", "excerpt": "Free forever"}]}}),
        ("unexpected_placeholder", {"body": "Hello [NAME_999], return within 30 days. [S1]", "citations": ["S1"]}),
        ("cosmetics_overgeneralization", {"body": "Cosmetics are non-returnable and not eligible for returns. [S1]", "citations": ["S1"]}),
        ("answerable_false_leak", {"body": "We have no policy covering this. [S1]", "citations": ["S1"], "answerable": False}),
    ]

    for tag, payload in bad_payloads:
        class BadInjectedLLM:
            configured = True
            def generate(self, *args, **kwargs):
                return dict(payload)

        r_bad, _, store_bad, c_bad = _make_runner(tmp_path / f"bad_{tag}", monkeypatch, {})
        r_bad.llm_client = BadInjectedLLM()
        try:
            res = r_bad.run("What is your standard return window?", _ctx(), run_id=f"postgen-{tag}")
            assert res["action"] == "manual_fallback", tag
            assert res["draft_body"] is None, tag
            assert res["draft_kind"] is None, tag
            assert any(c in res["reason_codes"] for c in ("grounding_failed", "llm_invalid_output")), (tag, res["reason_codes"])
            saved_bad = store_bad.get_run(f"postgen-{tag}")
            assert saved_bad is not None and saved_bad["draft_body"] is None, tag
            assert saved_bad["action"] == "manual_fallback", tag
        finally:
            c_bad.close()


def test_shared_safety_module_exports_and_engine_runner_parity(tmp_path: Path, monkeypatch):
    from apps.ai_service import engine as engine_mod
    from apps.core_backend import safety

    assert engine_mod.PLACEHOLDER is safety.PLACEHOLDER
    assert engine_mod.FACTUAL_COMMITMENT is safety.FACTUAL_COMMITMENT
    assert engine_mod.SENSITIVE_AUTHORITY_PATTERN is safety.SENSITIVE_AUTHORITY_PATTERN

    class StubModel:
        def predict(self, text):
            return {"intent": "return_policy", "confidence": 0.95, "margin": 0.85, "score_kind": "uncalibrated_softmax", "model_version": "v1.0.0", "model_mode": "trained", "verified": True, "top_k": [{"intent": "return_policy", "probability": 0.95}]}

    class ForbiddenLLM:
        def generate(self, *args, **kwargs):
            raise AssertionError("LLM must not be called")

    eng = engine_mod.Engine(StubModel(), StubRetriever(), ForbiddenLLM(), {"release_id": "test"}, policy={"supported_12_intents": ["return_policy"], "sensitive_action_intents": ["request_refund"], "all_46_labels": ["return_policy", "human_agent"], "default_confidence_threshold": 0.7, "default_margin_threshold": 0.1})
    analysis = eng.analyse({"message": "What are the customs import duties and unratified 2022 rules for international shipping?", "as_of": "2026-11-13T00:00:00+00:00"})
    assert analysis["routing"]["recommendation"] == "escalate"
    assert "insufficient_evidence" in analysis["routing"]["reason_codes"]
    assert "no_valid_document" in analysis["routing"]["reason_codes"]

    eng_benign = eng.analyse({"message": "I bought this item in 2025, what is the current 2026 return policy?", "as_of": "2026-11-13T00:00:00+00:00"})
    assert eng_benign["routing"]["recommendation"] == "draft"


def test_typed_fault_propagation_encoder_and_ml_timeout_parity(tmp_path: Path, monkeypatch):
    from apps.ai_service.engine import Engine
    from apps.core_backend.intent.schemas import IntentPrediction

    class FaultRetriever:
        eligible_versions = []
        def __init__(self, payload: dict[str, Any]):
            self._payload = payload
        def retrieve(self, *args, **kwargs):
            return dict(self._payload)

    class OkModel:
        def predict(self, text):
            return {"intent": "return_policy", "confidence": 0.95, "margin": 0.85, "score_kind": "uncalibrated_softmax", "model_version": "v1.0.0", "model_mode": "trained", "verified": True, "top_k": [{"intent": "return_policy", "probability": 0.95}]}

    class ForbiddenLLM:
        def generate(self, *args, **kwargs):
            raise AssertionError("LLM must not be called")

    for payload, expected_code, expected_engine_status in [
        ({"status": "encoder_unavailable", "evidence": [], "reason_codes": ["encoder_unavailable"], "has_conflict": False}, "encoder_unavailable", "abstained"),
        ({"status": "encoder_failure", "evidence": [], "reason_codes": ["encoder_failure", "encoder_failed"], "has_conflict": False}, "encoder_failure", "escalation_recommended"),
    ]:
        eng = Engine(OkModel(), FaultRetriever(payload), ForbiddenLLM(), {"release_id": "test"}, policy={"supported_12_intents": ["return_policy"], "sensitive_action_intents": ["request_refund"], "all_46_labels": ["return_policy"], "default_confidence_threshold": 0.7, "default_margin_threshold": 0.1})
        draft_res = eng.draft({"message": "What is your return policy?", "as_of": "2026-11-13T00:00:00+00:00"})
        assert draft_res["status"] == expected_engine_status
        assert "insufficient_evidence" in draft_res["reason_codes"]
        assert expected_code in draft_res["reason_codes"]
        if expected_code == "encoder_failure":
            assert "no_valid_document" not in draft_res["reason_codes"]
        else:
            assert "no_valid_document" in draft_res["reason_codes"]

        r_run, spy, _, c_run = _make_runner(tmp_path / expected_code, monkeypatch, {}, retriever=FaultRetriever(payload))
        try:
            rr = r_run.run("What is your return policy?", _ctx(), run_id=f"fault-{expected_code}")
            assert rr["action"] == "escalate"
            assert "insufficient_evidence" in rr["reason_codes"]
            assert expected_code in rr["reason_codes"]
            assert spy.calls == []
        finally:
            c_run.close()

    # Actual IntentClient -> IntentPrediction -> decide_route -> PipelineRunner MockTransport round-trip regressions
    def run_http_fault_case(case_id: str, handler):
        r_ml, spy_ml, _, c_ml = _make_runner(tmp_path / f"ml_{case_id}", monkeypatch, {})
        mock_http = httpx.Client(transport=httpx.MockTransport(handler))
        r_ml.intent_client = IntentClient(base_url="http://ml-service", expected_model_version="v2.0.0", http_client=mock_http)
        try:
            pred = r_ml.intent_client.classify_intent("Track order", request_id=f"req-{case_id}")
            res = r_ml.run("Track order", _ctx(), run_id=f"ml-{case_id}")
            assert spy_ml.calls == []
            return pred, res
        finally:
            mock_http.close()
            c_ml.close()

    def timeout_handler(req):
        raise httpx.ReadTimeout("", request=req)

    pred_to, res_to = run_http_fault_case("read_timeout_empty_msg", timeout_handler)
    assert pred_to.failure_code == "ml_timeout"
    assert res_to["action"] == "manual_fallback"
    assert "ml_timeout" in res_to["reason_codes"]
    assert "ml_unavailable" in res_to["reason_codes"]

    pred_504, res_504 = run_http_fault_case(
        "http_504_timeout",
        lambda req: httpx.Response(504, headers={"X-SupportIQ-Error-Code": "ml_timeout"}, json={"detail": {"error_code": "ml_timeout"}}),
    )
    assert pred_504.failure_code == "ml_timeout"
    assert res_504["action"] == "manual_fallback"
    assert "ml_timeout" in res_504["reason_codes"]
    assert "ml_unavailable" in res_504["reason_codes"]

    pred_503, res_503 = run_http_fault_case(
        "http_503_runtime",
        lambda req: httpx.Response(503, headers={"X-SupportIQ-Error-Code": "ml_error"}, json={"detail": {"error_code": "ml_error"}}),
    )
    assert pred_503.failure_code == "ml_error"
    assert res_503["action"] == "manual_fallback"
    assert "ml_error" in res_503["reason_codes"]
    assert "ml_unavailable" in res_503["reason_codes"]

    def connect_err_handler(req):
        raise httpx.ConnectError("connection refused", request=req)

    pred_conn, res_conn = run_http_fault_case("connect_error", connect_err_handler)
    assert pred_conn.failure_code == "ml_error"
    assert res_conn["action"] == "manual_fallback"
    assert "ml_error" in res_conn["reason_codes"]
    assert "ml_unavailable" in res_conn["reason_codes"]

    pred_bad, res_bad = run_http_fault_case(
        "invalid_payload",
        lambda req: httpx.Response(200, json={"intent": "return_policy", "confidence": "not-a-float", "model_version": "v2.0.0"}),
    )
    assert pred_bad.failure_code == "invalid_model_output"
    assert res_bad["action"] == "manual_fallback"
    assert "invalid_model_output" in res_bad["reason_codes"]
    assert "ml_unavailable" in res_bad["reason_codes"]



