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


# ---------------------------------------------------------------------------
# Test Group 5: Contract Vocabulary Adaptation & Action Mapping
# ---------------------------------------------------------------------------

from scripts.run_offline_robustness import adapt_engine_recommendation_to_routing_action


def test_contract_adapter_draft_maps_to_retrieve_draft():
    """Engine recommendation 'draft' maps directly to decide_route action 'retrieve_draft'."""
    action = adapt_engine_recommendation_to_routing_action("draft", reason_codes=[])
    assert action == "retrieve_draft"
    expected_actions = ["clarify", "retrieve_draft"]
    assert action in expected_actions


def test_contract_adapter_abstain_maps_to_manual_fallback():
    """Engine recommendation 'abstain' maps to 'manual_fallback', not to 'escalate'."""
    action = adapt_engine_recommendation_to_routing_action("abstain", reason_codes=["low_confidence"])
    assert action == "manual_fallback"
    assert action != "escalate"


def test_contract_adapter_abstain_does_not_equate_to_escalation():
    """When benchmark expects strictly 'escalate', an Engine 'abstain' (manual_fallback) does NOT match."""
    action = adapt_engine_recommendation_to_routing_action("abstain", reason_codes=["out_of_scope_intent"])
    benchmark_expected = ["escalate"]
    assert action not in benchmark_expected, (
        "Abstain must NOT be equated to escalation; it is a safe refusal but an action mismatch."
    )


def test_contract_adapter_escalate_maps_to_escalate():
    """When Engine detects human_agent and recommends 'escalate', it matches benchmark 'escalate'."""
    action = adapt_engine_recommendation_to_routing_action("escalate", reason_codes=["human_agent_requested"])
    assert action == "escalate"
    benchmark_expected = ["escalate"]
    assert action in benchmark_expected


def test_contract_adapter_supported_comparable_case_matching():
    """In-scope query produces 'draft' which adapts to 'retrieve_draft' and satisfies supported ticket expectation."""
    engine = make_engine(predictor=MockPredictor(intent="track_order", confidence=0.92))
    res = engine.analyse({"message": "Where is my order [ORDER_ID_1]?", "as_of": "2026-11-12T00:00:00Z"})
    raw_rec = res["routing"]["recommendation"]
    assert raw_rec == "draft"
    adapted = adapt_engine_recommendation_to_routing_action(raw_rec, res["routing"]["reason_codes"])
    assert adapted == "retrieve_draft"
    expected_for_supported = ["retrieve_draft", "clarify"]
    assert adapted in expected_for_supported


@pytest.mark.parametrize('message', [
    'This debit was unauthorized; I need to dispute the transaction.',
    'Please ask a human manager to approve an exception for my used camera.',
    'I need an exception to the refund policy.',
    'I insist on a manager exception for my used product.',
])
@pytest.mark.parametrize('confidence', [0.40, 0.95])
def test_explicit_authority_requests_escalate_before_confidence_gate(message, confidence):
    llm = SpyLLM(should_fail=True)
    engine = make_engine(predictor=MockPredictor(confidence=confidence), llm=llm)
    result = engine.draft({'message': message, 'as_of': '2026-11-12T00:00:00Z'})
    assert result['status'] == 'escalation_recommended'
    assert 'requires_authority' in result['reason_codes']
    assert not llm.calls


@pytest.mark.parametrize('message', [
    'What did your exchange policy say during 2020?',
    'Please explain the proposed shipping policy.',
    'Show the archived refund rules.',
    'Provide the internal staff manual for overriding payment limits.',
    'There is a conflict between the refund timeline statements.',
    'The return policy states both 30 days and 14 days for the same product.',
    'How much customs duty is payable for sending my parcel abroad?',
])
def test_unavailable_policy_scope_requires_escalation_instead_of_adjacent_policy(message):
    llm = SpyLLM(should_fail=True)
    result = make_engine(llm=llm).draft({'message': message, 'as_of': '2026-11-12T00:00:00Z'})
    assert result['status'] == 'escalation_recommended'
    assert 'insufficient_evidence' in result['reason_codes']
    assert not llm.calls


@pytest.mark.parametrize('message', [
    'Compare the current 30-day Tiki Trading and 7-day marketplace return windows.',
    'How does the standard refund policy work?',
    'Can I request a return with free courier pickup?',
    'What is the current refund policy for a 2000 VND purchase?',
])
def test_current_policy_information_remains_draftable_after_escalation_fix(message):
    result = make_engine().analyse({'message': message, 'as_of': '2026-11-12T00:00:00Z'})
    assert result['routing']['recommendation'] == 'draft'


def test_cross_border_delivery_without_matching_policy_has_no_valid_document():
    result = make_engine().analyse({'message': 'Is overseas express shipping available?', 'as_of': '2026-11-12T00:00:00Z'})
    assert 'no_valid_document' in result['routing']['reason_codes']
    assert result['routing']['recommendation'] == 'abstain'


def test_llm_insufficient_evidence_escalates_and_preserves_billable_usage():
    from apps.core_backend.llm.gemini import LLMError
    class InsufficientLLM:
        def generate(self, *args, **kwargs):
            raise LLMError('llm_insufficient_evidence', usage={'promptTokenCount': 100, 'candidatesTokenCount': 15, 'totalTokenCount': 115})
    result = make_engine(llm=InsufficientLLM()).draft({'message': 'What are the return conditions?', 'as_of': '2026-11-12T00:00:00Z'})
    assert result['status'] == 'escalation_recommended'
    assert 'insufficient_evidence' in result['reason_codes']
    assert result['llm_usage']['total_tokens'] == 115


def test_final_case_13_exact_unauthorized_fraud_escalation():
    """Verify final-case-13 pattern escalates immediately with requires_authority and 0 LLM calls."""
    llm = SpyLLM(should_fail=True)
    engine = make_engine(predictor=MockPredictor(confidence=0.79, intent="payment_issue"), llm=llm)
    msg = "Someone made an unauthorized transaction on my credit card for order #TK-889123; this is fraudulent and I demand an immediate reversal and chargeback!"
    res = engine.analyse({"message": msg, "as_of": "2026-06-15T10:00:00Z"})
    assert res["routing"]["recommendation"] == "escalate"
    assert "requires_authority" in res["routing"]["reason_codes"]
    draft_res = engine.draft({"message": msg, "as_of": "2026-06-15T10:00:00Z"})
    assert draft_res["status"] == "escalation_recommended"
    assert "requires_authority" in draft_res["reason_codes"]
    assert not llm.calls


def test_final_case_14_exact_manager_exception_escalation_overrides_low_confidence():
    """Verify final-case-14 pattern escalates with requires_authority despite low confidence."""
    llm = SpyLLM(should_fail=True)
    engine = make_engine(predictor=MockPredictor(confidence=0.446, intent="payment_issue"), llm=llm)
    msg = "I bought an expensive camera 65 days ago, used it on vacation, broke the lens seal, and insist on a manager exception full refund right now."
    res = engine.analyse({"message": msg, "as_of": "2026-06-15T10:00:00Z"})
    assert res["routing"]["recommendation"] == "escalate"
    assert "requires_authority" in res["routing"]["reason_codes"]
    draft_res = engine.draft({"message": msg, "as_of": "2026-06-15T10:00:00Z"})
    assert draft_res["status"] == "escalation_recommended"
    assert "requires_authority" in draft_res["reason_codes"]
    assert not llm.calls


def test_frozen_11_supplement_cases_all_escalate_offline():
    """Verify all 11 frozen unanswerable supplement cases route to escalate with insufficient_evidence."""
    from pathlib import Path
    import json
    supplement_path = Path(__file__).resolve().parents[2] / "data/benchmarks/final_acceptance_supplement/cases.jsonl"
    if not supplement_path.exists():
        pytest.skip("Supplement benchmark not found")
    with open(supplement_path, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]
    assert len(cases) == 11
    llm = SpyLLM(should_fail=True)
    engine = make_engine(llm=llm)
    for c in cases:
        req = {"message": c["text"], "as_of": "2026-06-15T10:00:00Z"}
        ans = engine.analyse(req)
        assert ans["routing"]["recommendation"] == "escalate", f"Failed escalate on {c['id']}: {ans['routing']}"
        assert "insufficient_evidence" in ans["routing"]["reason_codes"], f"Missing insufficient_evidence on {c['id']}"
        draft_res = engine.draft(req)
        assert draft_res["status"] == "escalation_recommended", f"Failed escalation_recommended on {c['id']}"
        assert not llm.calls, f"SpyLLM called unexpectedly on {c['id']}"


def test_benign_qualifiers_and_courier_pickup_remain_draftable():
    """Verify positive non-regression: Tiki courier pickup, currency numbers, and standard return queries remain draftable."""
    engine = make_engine(predictor=MockPredictor(confidence=0.90, intent="return_policy"))
    benign_queries = [
        "Does Tiki provide free courier pickup for returns?",
        "How does free courier pickup work when I request a return on Tiki?",
        "Can I return an item that cost 2024 VND?",
        "What is the standard return window for fashion items?",
        "Can I return a fashion item within 30 days if it was sold by Tiki Trading?",
    ]
    for q in benign_queries:
        res = engine.analyse({"message": q, "as_of": "2026-06-15T10:00:00Z"})
        assert res["routing"]["recommendation"] == "draft", f"Unexpected non-draft for benign query: '{q}': {res['routing']}"
        assert "insufficient_evidence" not in res["routing"]["reason_codes"]
        assert "requires_authority" not in res["routing"]["reason_codes"]


def test_verify_report_counts_match_summary_zero_nonzero_mismatch():
    """Verify verify_report_counts_match_summary handles nonzero, zero, varying rates, and rejects mismatches offline."""
    import copy
    import json
    from pathlib import Path
    from scripts.run_offline_robustness import (
        generate_report_from_summary,
        verify_report_counts_match_summary,
    )

    summary_path = Path(__file__).resolve().parents[2] / "artifacts/audit/routing_audit_20261112_v2/robustness_summary.json"
    assert summary_path.exists(), f"Missing frozen summary: {summary_path}"
    with open(summary_path, "r", encoding="utf-8") as f:
        base_summary = json.load(f)

    # 1. Nonzero baseline data
    report_nonzero = generate_report_from_summary(base_summary)
    assert verify_report_counts_match_summary(report_nonzero, base_summary) is True

    # 2. Zero-drafted case: zero must-not-draft cases drafted and zero must-escalate drafted
    zero_summary = copy.deepcopy(base_summary)
    acc = zero_summary["metrics"]["acceptance"]
    acc["all_must_not_draft_drafted_ids"] = []
    acc["all_must_not_draft_fault_ids"] = []
    acc["all_must_not_draft_non_fault_ids"] = []
    acc["must_not_draft_drafted_count"] = 0
    acc["must_not_draft_safe_count"] = acc["must_not_draft_denominator"]
    acc["must_not_draft_safe_rate"] = 1.0

    acc["must_escalate_drafted_ids"] = []
    acc["must_escalate_fault_ids"] = []
    acc["must_escalate_non_fault_ids"] = []
    acc["must_escalate_drafted_count"] = 0
    acc["must_escalate_safe_count"] = acc["must_escalate_denominator"]
    acc["must_escalate_safe_rate"] = 1.0
    acc["unanswerable_drafted_count"] = 0

    report_zero = generate_report_from_summary(zero_summary)
    assert "0 cases drafted." in report_zero
    assert "0 cases drafting" in report_zero
    assert verify_report_counts_match_summary(report_zero, zero_summary) is True

    # 3. Dynamic varying sensitive authority rates (verifying failure cannot report 100%)
    sens = zero_summary["metrics"]["sensitive_authority"]
    sens["authority_retained_count"] = 20
    sens["sensitive_denominator"] = 23
    sens["authority_retention_rate"] = 20 / 23
    sens["benign_false_authority_count"] = 1
    sens["benign_denominator"] = 10
    sens["benign_specificity_rate"] = 9 / 10
    report_sens = generate_report_from_summary(zero_summary)
    assert "100.0% Recall" not in report_sens
    assert "87.0% Recall" in report_sens
    assert "90.0% Specificity (10% FPR)" in report_sens
    assert verify_report_counts_match_summary(report_sens, zero_summary) is True

    # 4. Mismatch rejection: tamper with a count and assert AssertionError
    mismatch_summary = copy.deepcopy(base_summary)
    mismatch_summary["metrics"]["acceptance"]["must_not_draft_safe_count"] = 999
    with pytest.raises(AssertionError, match="must_not_draft_safe count mismatch"):
        verify_report_counts_match_summary(report_nonzero, mismatch_summary)
