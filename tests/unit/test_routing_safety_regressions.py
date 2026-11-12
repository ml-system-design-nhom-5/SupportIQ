"""Regression tests for Worker A: current-model robustness, safe routing, and authority retention.

Verifies:
1. Authority retention across fraud, chargeback, dispute, lawsuit, unauthorized debit, and policy exceptions.
2. Sticky manager authority across staff intent overrides (both sensitive->non-sensitive and non-sensitive->sensitive).
3. Elimination of unsafe draft recommendations on unsupported actions (e.g. online pickup) and out-of-domain queries.
4. Offline evaluation guarantees: LLM is a spy that raises if invoked during abstained or non-draft routing.
5. In-scope query coverage: safe routing does not universally abstain on supported clean queries.
"""

import math
import pytest
from types import SimpleNamespace
from datetime import datetime, timezone

from apps.ai_service.engine import Engine


class SpyLLM:
    """Spy LLM that records calls or fails when draft generation is forbidden."""
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.calls = []

    def generate(self, message, intent, evidence, business_context=None):
        if self.should_fail:
            raise AssertionError("LLM must not be called during offline abstained/escalated routing evaluation")
        self.calls.append({"message": message, "intent": intent, "evidence": evidence})
        return {
            "body": f"Draft response for {intent}. [S1]",
            "input_snapshot": {
                "sources": [
                    {
                        "source_id": "S1",
                        "source_type": "policy",
                        "document_id": evidence[0]["document_id"] if evidence else "POL-1",
                        "version": evidence[0]["version"] if evidence else "1.0",
                        "excerpt": evidence[0]["snippet"] if evidence else "Policy excerpt",
                    }
                ]
            },
            "usage": {"promptTokenCount": 50, "candidatesTokenCount": 20, "totalTokenCount": 70},
            "latency_seconds": 0.1,
        }


class MockRetriever:
    def __init__(self, evidence=None, has_conflict=False):
        self._evidence = evidence
        self.has_conflict = has_conflict
        self.eligible_versions = [
            SimpleNamespace(
                doc_id="POL-RET-001",
                version="1.0",
                title="Return Policy",
                content="30-day returns in original packaging.",
                metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to=None),
            ),
            SimpleNamespace(
                doc_id="POL-REFUND-001",
                version="1.0",
                title="Refund Policy",
                content="Refunds require inspection.",
                metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to=None),
            ),
            SimpleNamespace(
                doc_id="POL-ORD-002",
                version="1.0",
                title="Order Cancellation",
                content="Orders in processing can be canceled.",
                metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to=None),
            ),
            SimpleNamespace(
                doc_id="POL-RET-002",
                version="1.0",
                title="Return and Exchange Request Process and Steps on Tiki App",
                content="Shipping couriers will pick up the item directly from the customer's address for free within 1-2 business days.",
                metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to=None),
            ),
        ]

    def retrieve(self, message, intent, role="agent", current_time=None):
        if self._evidence is not None:
            return {"status": "success", "evidence": self._evidence, "has_conflict": self.has_conflict}
        # Default mock evidence
        return {
            "status": "success",
            "evidence": [
                {
                    "document_id": "POL-RET-001",
                    "version": "1.0",
                    "title": "Return Policy",
                    "excerpt": "30-day returns in original packaging.",
                    "score": 0.85,
                }
            ],
            "has_conflict": self.has_conflict,
        }


class MockPredictor:
    def __init__(self, intent="return_policy", confidence=0.92, margin=0.85, top_k=None):
        self.intent = intent
        self.confidence = confidence
        self.margin = margin
        self.top_k = top_k or [
            {"intent": intent, "probability": confidence},
            {"intent": "shipping_costs", "probability": max(0.0, 1.0 - confidence)},
        ]

    def predict(self, text):
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "margin": self.margin,
            "score_kind": "uncalibrated_softmax",
            "model_version": "v1.0.0",
            "model_mode": "trained",
            "verified": True,
            "top_k": self.top_k,
        }


def make_engine(predictor=None, retriever=None, llm=None, policy=None):
    from apps.core_backend.intent.routing import load_policy_v2
    import json
    from pathlib import Path

    pol_dict = policy
    if pol_dict is None:
        p_path = Path("apps/core_backend/config/policies/intent_policy.v2.json")
        pol_dict = json.loads(p_path.read_text(encoding="utf-8"))

    return Engine(
        model=predictor or MockPredictor(),
        retriever=retriever or MockRetriever(),
        llm=llm or SpyLLM(),
        versions={"release_id": "test-v1", "model_version": "v1.0.0"},
        policy=pol_dict,
    )


# ---------------------------------------------------------------------------
# Test Group 1: Authority Retention & Sensitive Scenario Coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phrase,scenario",
    [
        ("I was defrauded and demand immediate intervention", "fraud"),
        ("This transaction was fraudulent, look at my statement", "fraudulent"),
        ("I will file a lawsuit if my money is not returned", "lawsuit"),
        ("I am seeking advice from my lawyer regarding this contract", "lawyer"),
        ("I am preparing to take this dispute to court", "court"),
        ("I will dispute this charge with my credit card issuer", "dispute"),
        ("I noticed an unauthorized debit of $150 on my account", "unauthorized_debit"),
        ("This charge was not authorized by me", "not_authorized"),
        ("Can you make an exception for my return?", "make_exception"),
        ("I need an exception to the return policy window", "policy_exception"),
        ("I am requesting a refund exception due to special circumstances", "refund_exception"),
    ],
)
def test_sensitive_scenarios_trigger_requires_authority(phrase, scenario):
    """Every sensitive phrase (fraud, lawsuit, dispute, unauthorized, exception) must flag requires_authority."""
    # Predictor predicts a non-sensitive supported intent (e.g. return_policy)
    engine = make_engine(predictor=MockPredictor(intent="return_policy", confidence=0.88))
    res = engine.analyse({"message": phrase, "as_of": "2026-11-12T00:00:00Z"})
    assert "requires_authority" in res["routing"]["reason_codes"], (
        f"Scenario '{scenario}' ({phrase}) failed to trigger requires_authority in reason_codes: {res['routing']['reason_codes']}"
    )


def test_sticky_authority_retained_when_staff_overrides_to_nonsensitive_intent():
    """When a customer inquiry is sensitive, staff override to a non-sensitive intent (track_order) must retain requires_authority."""
    engine = make_engine(predictor=MockPredictor(intent="return_policy", confidence=0.90))
    res = engine.analyse({
        "message": "I demand an exception for my return window.",
        "as_of": "2026-11-12T00:00:00Z",
        "intent_override": "track_order",  # non-sensitive override
    })
    assert "requires_authority" in res["routing"]["reason_codes"], (
        "requires_authority was lost after non-sensitive intent override on a sensitive customer message!"
    )


def test_override_to_sensitive_intent_activates_requires_authority():
    """When customer inquiry is benign, staff override to a sensitive intent (request_refund) activates requires_authority."""
    engine = make_engine(predictor=MockPredictor(intent="track_order", confidence=0.95))
    res = engine.analyse({
        "message": "Where is my package right now?",
        "as_of": "2026-11-12T00:00:00Z",
        "intent_override": "request_refund",  # sensitive action intent
    })
    assert "requires_authority" in res["routing"]["reason_codes"], (
        "requires_authority was NOT activated when staff overrode to sensitive intent request_refund!"
    )


# ---------------------------------------------------------------------------
# Test Group 2: Unsafe Draft Recommendations & Out-Of-Domain Abstention
# ---------------------------------------------------------------------------

def test_unsupported_return_pickup_action_does_not_draft():
    """Scheduling a postal pickup for online return parcel (return_product_online) must not produce draft."""
    engine = make_engine()
    res = engine.analyse({
        "message": "How do I schedule a postal pickup for an online return parcel?",
        "as_of": "2026-11-12T00:00:00Z",
    })
    assert res["routing"]["recommendation"] != "draft", (
        f"Unsupported online pickup action was incorrectly recommended for draft: {res['routing']}"
    )
    assert "out_of_scope_intent" in res["routing"]["reason_codes"]


def test_positive_supported_return_courier_pickup_drafts_successfully():
    """Valid in-app courier pickup (POL-RET-002) is supported and must recommend draft without out_of_scope_intent."""
    courier_evidence = [
        {
            "document_id": "POL-RET-002",
            "version": "1.0",
            "title": "Return and Exchange Request Process and Steps on Tiki App",
            "excerpt": "Shipping couriers will pick up the item directly from the customer's address for free within 1-2 business days.",
            "score": 0.88,
        }
    ]
    engine = make_engine(
        predictor=MockPredictor(intent="return_policy", confidence=0.85),
        retriever=MockRetriever(evidence=courier_evidence),
    )
    res = engine.analyse({
        "message": "How does free courier pickup work when I request a return on Tiki?",
        "as_of": "2026-11-12T00:00:00Z",
    })
    assert res["routing"]["recommendation"] == "draft", (
        f"Supported courier return pickup was incorrectly blocked: {res['routing']}"
    )
    assert "out_of_scope_intent" not in res["routing"]["reason_codes"]
    assert any(d["document_id"] == "POL-RET-002" for d in res["documents"])


def test_positive_supported_home_pickup_drafts_successfully():
    """Customer asking about courier home address pickup under POL-RET-002 must draft without refusal."""
    courier_evidence = [
        {
            "document_id": "POL-RET-002",
            "version": "1.0",
            "title": "Return and Exchange Request Process and Steps on Tiki App",
            "excerpt": "Shipping couriers will pick up the item directly from the customer's address for free within 1-2 business days.",
            "score": 0.85,
        }
    ]
    engine = make_engine(
        predictor=MockPredictor(intent="return_policy", confidence=0.82),
        retriever=MockRetriever(evidence=courier_evidence),
    )
    res = engine.analyse({
        "message": "Can a shipping courier pick up my return item from my home address?",
        "as_of": "2026-11-12T00:00:00Z",
    })
    assert res["routing"]["recommendation"] == "draft", (
        f"Supported home courier return pickup was incorrectly blocked: {res['routing']}"
    )
    assert "out_of_scope_intent" not in res["routing"]["reason_codes"]


def test_out_of_domain_tax_return_abstains_safely():
    """Out-of-domain query 'income tax return' with sub-threshold retrieval relevance must abstain."""
    # Low relevance retrieval evidence (below 0.60 floor)
    low_evidence = [
        {"document_id": "POL-REFUND-001", "version": "1.0", "title": "Refund Rules", "excerpt": "Tiki refunds...", "score": 0.54}
    ]
    engine = make_engine(
        predictor=MockPredictor(intent="return_policy", confidence=0.70),
        retriever=MockRetriever(evidence=low_evidence),
    )
    res = engine.analyse({
        "message": "How do I file my income tax return?",
        "as_of": "2026-11-12T00:00:00Z",
    })
    assert res["routing"]["recommendation"] == "abstain", (
        f"Out-of-domain tax query did not abstain: {res['routing']}"
    )
    assert "no_valid_document" in res["routing"]["reason_codes"]


def test_multi_intent_account_closure_does_not_draft():
    """Multi-intent query asking to close account alongside return policy must escalate or abstain, not draft."""
    engine = make_engine()
    res = engine.analyse({
        "message": "What is your return policy and can I close my account?",
        "as_of": "2026-11-12T00:00:00Z",
    })
    assert res["routing"]["recommendation"] != "draft", (
        f"Multi-intent query with account closure was incorrectly recommended for draft: {res['routing']}"
    )


# ---------------------------------------------------------------------------
# Test Group 3: Offline Robustness & LLM Spy Protection
# ---------------------------------------------------------------------------

def test_offline_robustness_never_invokes_llm_on_abstained_query():
    """When routing abstains, Engine.draft() MUST NEVER invoke the LLM (spy fails immediately if called)."""
    forbidden_llm = SpyLLM(should_fail=True)
    # Low confidence predictor causes abstention
    engine = make_engine(
        predictor=MockPredictor(intent="return_policy", confidence=0.40, margin=0.05),
        llm=forbidden_llm,
    )
    result = engine.draft({
        "message": "What is your return policy?",
        "as_of": "2026-11-12T00:00:00Z",
    })
    assert result["status"] == "abstained"
    assert len(forbidden_llm.calls) == 0


def test_offline_robustness_never_invokes_llm_on_human_agent_escalation():
    """When routing escalates for human_agent, Engine.draft() MUST NEVER invoke the LLM."""
    forbidden_llm = SpyLLM(should_fail=True)
    engine = make_engine(
        predictor=MockPredictor(intent="human_agent", confidence=0.95, margin=0.90),
        llm=forbidden_llm,
    )
    result = engine.draft({
        "message": "I want to talk to a human agent.",
        "as_of": "2026-11-12T00:00:00Z",
    })
    assert result["status"] == "escalation_recommended"
    assert len(forbidden_llm.calls) == 0


# ---------------------------------------------------------------------------
# Test Group 4: In-Scope Supported Query Coverage (No Universal Abstention)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "intent,text",
    [
        ("track_order", "Where is my order [ORDER_ID_1]?"),
        ("delivery_time", "How long does standard delivery usually take?"),
        ("delivery_issue", "My package arrived with damaged packaging."),
        ("shipping_costs", "What are the shipping fees for standard delivery?"),
        ("return_policy", "What is your standard return policy and window?"),
        ("refund_policy", "What is the refund timeline for credit card payments?"),
        ("refund_status", "Has the refund for my returned item been processed?"),
    ],
)
def test_clean_in_scope_queries_remain_draftable(intent, text):
    """Clean, high-confidence in-scope queries must recommend draft and maintain coverage."""
    engine = make_engine(predictor=MockPredictor(intent=intent, confidence=0.92, margin=0.85))
    res = engine.analyse({"message": text, "as_of": "2026-11-12T00:00:00Z"})
    assert res["routing"]["recommendation"] == "draft", (
        f"In-scope query '{text}' for intent '{intent}' was rejected: {res['routing']}"
    )
    assert res["is_in_scope"] is True
