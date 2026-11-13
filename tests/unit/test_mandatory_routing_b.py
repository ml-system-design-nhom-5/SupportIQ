"""Focused RED->GREEN unit tests for general mandatory routing & Engine/HTTP parity (Task B)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.ai_service.engine import Engine
from apps.backend.tickets.jobs import AI_REASONS
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.routing import (
    ESCALATED_34_INTENTS,
    INTENT_TO_QUEUE_MAP,
    decide_route,
)
from apps.core_backend.intent.schemas import IntentPolicy, IntentPrediction, RoutingContext
import apps.ml_inference.app as ml_app

POLICY_PATH = Path(__file__).resolve().parents[2] / "apps/core_backend/config/policies/intent_policy.v2.json"


def _load_policy_dict() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _load_policy_obj() -> IntentPolicy:
    return IntentPolicy.model_validate(_load_policy_dict())


class SpyLLM:
    def __init__(self):
        self.called = False

    def generate(self, *args, **kwargs):
        self.called = True
        raise AssertionError("LLM must never be called for non-draft routing outcomes")


class StubModel:
    def __init__(
        self,
        intent: str,
        confidence: float = 0.92,
        margin: float = 0.80,
        *,
        selective_accepted: bool | None = None,
        rejected_by_experimental_adapter: bool | None = None,
        rejector_decision: str | None = None,
        top_k: list[dict] | None = None,
    ):
        self._pred = {
            "intent": intent,
            "confidence": confidence,
            "margin": margin,
            "top_k": top_k or [{"intent": intent, "probability": confidence}],
            "score_kind": "calibrated_probability",
            "model_mode": "trained",
            "verified": True,
        }
        if selective_accepted is not None:
            self._pred["selective_accepted"] = selective_accepted
        if rejected_by_experimental_adapter is not None:
            self._pred["rejected_by_experimental_adapter"] = rejected_by_experimental_adapter
        if rejector_decision is not None:
            self._pred["rejector_decision"] = rejector_decision

    def predict(self, message: str) -> dict:
        return dict(self._pred)


class StubRetriever:
    def __init__(self, evidence: list[dict] | None = None, *, has_conflict: bool = False):
        self.relevance_threshold = 0.55
        self.eligible_versions = [
            SimpleNamespace(
                doc_id="POL-RET-001",
                version="1",
                metadata=SimpleNamespace(valid_from="2025-01-01", valid_to="2026-12-31"),
            )
        ]
        self._evidence = (
            [
                {
                    "document_id": "POL-RET-001",
                    "version": "1",
                    "title": "Return Policy",
                    "excerpt": "Tiki Trading items can be returned via free Tiki courier pickup within 30 days.",
                    "score": 0.92,
                }
            ]
            if evidence is None
            else evidence
        )
        self._has_conflict = has_conflict

    def retrieve(self, query: str, intent: str, *, role: str = "agent", current_time=None) -> dict:
        return {
            "evidence": list(self._evidence),
            "has_conflict": self._has_conflict,
            "reason_codes": [],
        }


def _make_engine(model: StubModel, retriever: StubRetriever | None = None) -> tuple[Engine, SpyLLM]:
    llm = SpyLLM()
    engine = Engine(
        model=model,
        retriever=retriever or StubRetriever(),
        llm=llm,
        versions={"release_id": "test-rel", "model_version": "test-m1"},
        policy=_load_policy_dict(),
    )
    return engine, llm


def _req(message: str, **extra) -> dict:
    payload = {
        "message": message,
        "as_of": datetime(2026, 6, 1, tzinfo=timezone.utc).isoformat(),
        "order_context": {},
    }
    payload.update(extra)
    return payload


@pytest.mark.parametrize("outside_intent", sorted(ESCALATED_34_INTENTS))
def test_engine_escalates_all_recognized_outside_scope_34_intents_preserving_ai_reasons(outside_intent: str):
    """All 34 recognized outside-product-scope taxonomy intents must escalate without LLM generation."""
    engine, llm = _make_engine(StubModel(intent=outside_intent, confidence=0.92, margin=0.80))
    analysis = engine.analyse(_req("Customer asks about an escalated non-supported queue topic."))

    assert analysis["routing"]["recommendation"] == "escalate"
    assert "out_of_scope_intent" in analysis["routing"]["reason_codes"]
    assert set(analysis["routing"]["reason_codes"]) <= AI_REASONS

    draft_res = engine.draft(_req("Customer asks about an escalated non-supported queue topic."))
    assert draft_res["status"] == "escalation_recommended"
    assert llm.called is False


def test_engine_keeps_safe_abstention_distinct_from_escalation():
    """Selective rejection, non-taxonomy OOD, low confidence, missing docs, and conflicts abstain safely."""
    cases = [
        (
            StubModel("return_policy", 0.92, 0.85, selective_accepted=False, rejected_by_experimental_adapter=True, rejector_decision="reject"),
            StubRetriever(),
            "What is your return window?",
        ),
        (
            StubModel("unmapped_unknown_intent", 0.90, 0.80),
            StubRetriever(),
            "Arbitrary out of taxonomy message.",
        ),
        (
            StubModel("return_policy", 0.35, 0.02),
            StubRetriever(),
            "Blurry unclear support text.",
        ),
        (
            StubModel("return_policy", 0.90, 0.80),
            StubRetriever(evidence=[]),
            "Unsupported question lacking policy coverage.",
        ),
        (
            StubModel("return_policy", 0.90, 0.80),
            StubRetriever(has_conflict=True),
            "What is the standard return window?",
        ),
        (
            StubModel("return_policy", 0.80, 0.70),
            StubRetriever(evidence=[{"document_id": "POL-RET-001", "version": "1", "title": "Return", "excerpt": "Goods return", "score": 0.40}]),
            "How do I file my income tax return?",
        ),
    ]
    for model, retriever, message in cases:
        engine, llm = _make_engine(model, retriever)
        analysis = engine.analyse(_req(message))
        assert analysis["routing"]["recommendation"] == "abstain", f"Expected abstain for {message}: {analysis['routing']}"
        assert set(analysis["routing"]["reason_codes"]) <= AI_REASONS
        assert engine.draft(_req(message))["status"] == "abstained"
        assert llm.called is False


@pytest.mark.parametrize(
    "handoff_msg",
    [
        "Transfer me to a live customer support representative.",
        "I want a human staff member right now.",
        "Connect me with a real person immediately.",
    ],
)
def test_engine_human_agent_representative_phrases_escalate(handoff_msg: str):
    """Explicit human representative requests escalate even if classifier mispredicts customer_service."""
    engine, llm = _make_engine(StubModel(intent="customer_service", confidence=0.98, margin=0.90))
    analysis = engine.analyse(_req(handoff_msg))

    assert analysis["routing"]["recommendation"] == "escalate"
    assert "human_agent_requested" in analysis["routing"]["reason_codes"]
    assert set(analysis["routing"]["reason_codes"]) <= AI_REASONS
    assert engine.draft(_req(handoff_msg))["status"] == "escalation_recommended"
    assert llm.called is False


@pytest.mark.parametrize(
    "scope_gap_msg",
    [
        "What is the unratified compensation guideline for late shipments?",
        "Provide the confidential audit policy for discretionary credits.",
        "Does free cancellation apply if one section says free and another section says a 10% fee?",
    ],
)
def test_engine_general_policy_scope_gaps_escalate(scope_gap_msg: str):
    """Unratified guidelines, confidential audit policies, and contradictory policy sections escalate."""
    engine, llm = _make_engine(StubModel(intent="return_policy", confidence=0.88, margin=0.70))
    analysis = engine.analyse(_req(scope_gap_msg))

    assert analysis["routing"]["recommendation"] == "escalate"
    assert "insufficient_evidence" in analysis["routing"]["reason_codes"]
    assert set(analysis["routing"]["reason_codes"]) <= AI_REASONS
    assert engine.draft(_req(scope_gap_msg))["status"] == "escalation_recommended"
    assert llm.called is False


@pytest.mark.parametrize(
    "clean_msg,predicted_intent",
    [
        ("How do I arrange a free Tiki courier pickup for my return?", "return_policy"),
        ("What are the shipping fee rates for standard delivery?", "shipping_costs"),
        ("Can I return a defective electronic item within 30 days?", "return_policy"),
    ],
)
def test_engine_preserves_clean_supported_draft_eligibility(clean_msg: str, predicted_intent: str):
    """General scope rules must NOT block legitimate supported inquiries."""
    engine, _ = _make_engine(StubModel(intent=predicted_intent, confidence=0.93, margin=0.80))
    analysis = engine.analyse(_req(clean_msg))

    assert analysis["routing"]["recommendation"] == "draft"


@pytest.mark.parametrize(
    "outside_action_msg",
    [
        "What is your return policy and can I also close my account?",
        "How do I schedule a postal pickup for my return?",
    ],
)
def test_engine_explicit_outside_scope_actions_escalate_without_llm(outside_action_msg: str):
    """Explicit account-closure or external postal-pickup actions escalate even on misclassified supported intent."""
    engine, llm = _make_engine(StubModel(intent="return_policy", confidence=0.85, margin=0.65))
    analysis = engine.analyse(_req(outside_action_msg))

    assert analysis["routing"]["recommendation"] == "escalate"
    assert "out_of_scope_intent" in analysis["routing"]["reason_codes"]
    assert set(analysis["routing"]["reason_codes"]) <= AI_REASONS
    assert engine.draft(_req(outside_action_msg))["status"] == "escalation_recommended"
    assert llm.called is False


def test_decide_route_valid_override_bypasses_low_confidence_while_preserving_gates():
    """Validated staff overrides bypass low ML confidence like selective veto, while keeping slot/authority/policy gates."""
    policy = _load_policy_obj()
    low_pred = IntentPrediction(
        intent="request_refund",
        confidence=0.35,
        margin=0.02,
        score_kind="calibrated_probability",
        model_version="v2.0.0",
    )

    unauth_ctx = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_1",
        intent_override="track_order",
        override_provenance={"actor_id": "sup_1", "reason": "confirmed"},
        extracted_slots={"order_id": "ORD-100"},
    )
    assert decide_route(low_pred, unauth_ctx, policy).action == "clarify"

    auth_missing_slot = RoutingContext(
        verified_scope="ticket:read intent:override",
        ticket_customer_id="cust_1",
        intent_override="track_order",
        override_provenance={"actor_id": "sup_1", "reason": "confirmed tracking question"},
        extracted_slots={},
    )
    slot_dec = decide_route(low_pred, auth_missing_slot, policy)
    assert slot_dec.action == "clarify"
    assert "missing_order_id" in slot_dec.reason_codes

    auth_complete = RoutingContext(
        verified_scope="ticket:read intent:override",
        ticket_customer_id="cust_1",
        intent_override="track_order",
        override_provenance={"actor_id": "sup_1", "reason": "confirmed tracking question"},
        extracted_slots={"order_id": "ORD-100"},
    )
    ok_dec = decide_route(low_pred, auth_complete, policy)
    assert ok_dec.action == "retrieve_draft"
    assert ok_dec.final_intent == "track_order"
    assert ok_dec.target_queue == "manager"
    assert "requires_authority" in ok_dec.reason_codes
    assert ok_dec.must_human_approve is True
    assert ok_dec.can_execute_transaction is False

    unapproved_policy = policy.model_copy(update={"approved": False})
    assert decide_route(low_pred, auth_complete, unapproved_policy).action == "manual_fallback"


def test_http_predict_to_intent_client_and_decide_route_parity(monkeypatch):
    """End-to-end offline HTTP /predict -> IntentClient -> decide_route check."""
    policy = _load_policy_obj()
    canned_responses = {
        "supported return query": {
            "intent": "return_policy",
            "confidence": 0.91,
            "margin": 0.80,
            "top_k": [{"intent": "return_policy", "probability": 0.91}],
            "score_kind": "calibrated_probability",
            "model_version": "v2.0.0",
            "model_mode": "trained",
            "verified": True,
            "raw_confidence": 0.93,
            "raw_margin": 0.84,
            "raw_score_kind": "uncalibrated_softmax",
            "calibration_temperature": 1.1,
            "selective_accepted": True,
            "rejected_by_experimental_adapter": False,
            "rejector_decision": "accept",
        },
        "damaged delivery item": {
            "intent": "damaged_delivery",
            "confidence": 0.92,
            "margin": 0.82,
            "top_k": [{"intent": "damaged_delivery", "probability": 0.92}],
            "score_kind": "calibrated_probability",
            "model_version": "v2.0.0",
            "model_mode": "trained",
            "verified": True,
            "raw_confidence": 0.94,
            "raw_margin": 0.86,
            "raw_score_kind": "uncalibrated_softmax",
            "calibration_temperature": 1.1,
            "selective_accepted": True,
            "rejected_by_experimental_adapter": False,
            "rejector_decision": "accept",
        },
        "rejected query": {
            "intent": "return_policy",
            "confidence": 0.91,
            "margin": 0.80,
            "top_k": [{"intent": "return_policy", "probability": 0.91}],
            "score_kind": "calibrated_probability",
            "model_version": "v2.0.0",
            "model_mode": "trained",
            "verified": True,
            "raw_confidence": 0.91,
            "raw_margin": 0.80,
            "raw_score_kind": "uncalibrated_softmax",
            "calibration_temperature": 1.1,
            "selective_accepted": False,
            "rejected_by_experimental_adapter": True,
            "rejector_decision": "reject",
        },
    }

    class DummyContainer:
        model_version = "v2.0.0"
        verified_model_version = "v2.0.0"
        model_mode = "trained"
        verified = True
        calibration_schema_version = "temp_v1"
        id2label = {i: l for i, l in enumerate(sorted(policy.all_46_labels))}

        @staticmethod
        def is_ready():
            return True

        @staticmethod
        def is_trained_ready():
            return True

        @staticmethod
        def predict(text: str, temperature=None, calibrated: bool = True):
            return dict(canned_responses[text])

    monkeypatch.setattr(ml_app, "container", DummyContainer())
    tc = TestClient(ml_app.app)

    def _asgi_bridge(request: httpx.Request) -> httpx.Response:
        resp = tc.post(request.url.path, content=request.content, headers=dict(request.headers))
        return httpx.Response(status_code=resp.status_code, content=resp.content, headers=dict(resp.headers))

    client = IntentClient(
        base_url="http://ml-service",
        expected_model_version="v2.0.0",
        http_client=httpx.Client(transport=httpx.MockTransport(_asgi_bridge)),
    )
    base_ctx = RoutingContext(ticket_customer_id="cust_1", caller_customer_id="cust_1")

    dec_supported = decide_route(client.classify_intent("supported return query"), base_ctx, policy)
    assert dec_supported.action == "retrieve_draft"
    assert dec_supported.must_human_approve is True
    assert dec_supported.can_execute_transaction is False

    dec_outside = decide_route(client.classify_intent("damaged delivery item"), base_ctx, policy)
    assert dec_outside.action == "escalate"
    assert dec_outside.requested_team == INTENT_TO_QUEUE_MAP["damaged_delivery"]
    assert "recognized_outside_product_scope" in dec_outside.reason_codes

    dec_rejected = decide_route(client.classify_intent("rejected query"), base_ctx, policy)
    assert dec_rejected.action == "manual_fallback"
    assert "selective_rejected" in dec_rejected.reason_codes

    human_ctx = RoutingContext(ticket_customer_id="cust_1", caller_customer_id="cust_1", is_explicit_human_request=True)
    dec_human = decide_route(client.classify_intent("rejected query"), human_ctx, policy)
    assert dec_human.action == "escalate"
    assert dec_human.requested_team == "general_support"
