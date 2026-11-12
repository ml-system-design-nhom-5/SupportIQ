import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from apps.ai_service.engine import Engine
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.llm.gemini import SYSTEM_PROMPT


class MockModel:
    def __init__(self, intent="payment_issue", confidence=0.92, margin=0.85, top_k=None):
        self.intent = intent
        self.confidence = confidence
        self.margin = margin
        self.top_k = top_k or [
            {"intent": intent, "probability": confidence},
            {"intent": "track_order", "probability": 0.05},
        ]

    def predict(self, text):
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "margin": self.margin,
            "score_kind": "uncalibrated_softmax",
            "model_mode": "trained",
            "verified": True,
            "model_version": "v1.0.0",
            "top_k": self.top_k,
        }


class MockRetriever:
    def __init__(self, evidence=None, has_conflict=False):
        self.evidence = evidence or []
        self.has_conflict = has_conflict
        self.eligible_versions = [
            SimpleNamespace(
                doc_id=item.get("document_id", item.get("doc_id")),
                version=item.get("version", "1.0"),
                title=item.get("title", ""),
                content=item.get("excerpt", ""),
                metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to="2026-12-31T23:59:59Z"),
            )
            for item in self.evidence
        ]

    def retrieve(self, message, intent, role="agent", current_time=None):
        return {
            "status": "success" if self.evidence else "no_match",
            "evidence": self.evidence,
            "has_conflict": self.has_conflict,
        }


class MockLLM:
    def __init__(self, body="Response body [S1]", sources=None, is_clarification=False):
        self.body = body
        self.sources = sources or [
            {"source_id": "S1", "source_type": "policy", "document_id": "POL-RET-003", "version": "2.0", "excerpt": "Excerpt"}
        ]
        self.is_clarification = is_clarification

    def generate(self, message, intent, evidence, business_context=None):
        return {
            "body": self.body,
            "input_snapshot": {"sources": self.sources},
            "is_clarification": self.is_clarification,
            "latency_seconds": 0.05,
            "usage": {"promptTokenCount": 100, "candidatesTokenCount": 30},
        }


def make_engine(model=None, retriever=None, llm=None):
    policy = {
        "supported_12_intents": [
            "track_order", "cancel_order", "delivery_time", "delivery_issue",
            "shipping_costs", "return_policy", "return_product", "refund_policy",
            "request_refund", "refund_status", "payment_issue", "human_agent"
        ],
        "sensitive_action_intents": [
            "cancel_order", "request_refund", "return_product", "payment_issue"
        ],
        "default_confidence_threshold": 0.70,
        "default_margin_threshold": 0.10,
        "confidence_thresholds": {},
        "margin_thresholds": {},
    }
    versions = {
        "release_id": "rel-test-b2",
        "model_version": "v1.0.0",
        "model_mode": "trained",
        "verified": True,
        "kb_version": "kb-v2",
        "prompt_version": "grounded-v2",
        "routing_version": "policy-v2",
        "index_version": "bge-test",
    }
    return Engine(
        model=model or MockModel(),
        retriever=retriever or MockRetriever(),
        llm=llm or MockLLM(),
        versions=versions,
        policy=policy,
    )


def test_cosmetics_draft_without_unsealed_qualifier_fails_grounding():
    """Cosmetics source POL-RET-003 only excludes unsealed/opened items.
    A draft that overgeneralizes and asserts all cosmetics are non-returnable must fail grounding.
    """
    evidence = [{
        "document_id": "POL-RET-003",
        "version": "2.0",
        "title": "Restricted Return Categories",
        "excerpt": "Product categories that do not support returns due to change of mind include: Underwear, swimwear, cosmetics and chemicals with unsealed protective packaging...",
        "score": 0.85,
    }]
    sources = [{
        "source_id": "S1",
        "source_type": "policy",
        "document_id": "POL-RET-003",
        "version": "2.0",
        "excerpt": evidence[0]["excerpt"],
    }]
    # Overgeneralized draft omitting 'unsealed' packaging qualifier
    overgeneralized_draft = "Cosmetics and beauty products cannot be returned due to change of mind. [S1]"
    engine = make_engine(
        retriever=MockRetriever(evidence=evidence),
        llm=MockLLM(body=overgeneralized_draft, sources=sources),
    )

    req = {
        "message": "Can I return a cosmetic lotion I purchased?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    res = engine.draft(req)
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_cosmetics_draft_with_unsealed_qualifier_succeeds():
    """When the draft preserves the 'unsealed protective packaging' condition, it succeeds."""
    evidence = [{
        "document_id": "POL-RET-003",
        "version": "2.0",
        "title": "Restricted Return Categories",
        "excerpt": "Product categories that do not support returns due to change of mind include: Underwear, swimwear, cosmetics and chemicals with unsealed protective packaging...",
        "score": 0.85,
    }]
    sources = [{
        "source_id": "S1",
        "source_type": "policy",
        "document_id": "POL-RET-003",
        "version": "2.0",
        "excerpt": evidence[0]["excerpt"],
    }]
    proper_draft = "Cosmetics with unsealed protective packaging are not eligible for return due to change of mind. [S1]"
    engine = make_engine(
        retriever=MockRetriever(evidence=evidence),
        llm=MockLLM(body=proper_draft, sources=sources),
    )

    req = {
        "message": "Can I return a cosmetic lotion I purchased?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    res = engine.draft(req)
    assert res["status"] == "draft_ready"
    assert "grounding_failed" not in res["reason_codes"]


def test_chargeback_unauthorized_payment_fails_when_giving_duplicate_charge_advice():
    """An inquiry regarding an unauthorized transaction or chargeback must NOT receive
    generic duplicate-charge advice (e.g. automatic 48h refund under POL-PAY-004).
    """
    evidence = [{
        "document_id": "POL-PAY-004",
        "version": "1.0",
        "title": "Handling Double Deductions",
        "excerpt": "Duplicate charges are refunded within 48 business hours.",
        "score": 0.80,
    }]
    sources = [{
        "source_id": "S1",
        "source_type": "policy",
        "document_id": "POL-PAY-004",
        "version": "1.0",
        "excerpt": evidence[0]["excerpt"],
    }]
    unsuitable_draft = "If this inquiry concerns a duplicate charge, our system will automatically refund the excess within 48 business hours. [S1]"
    engine = make_engine(
        retriever=MockRetriever(evidence=evidence),
        llm=MockLLM(body=unsuitable_draft, sources=sources),
    )

    req = {
        "message": "I will initiate a chargeback for this unauthorized transaction.",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    res = engine.draft(req)
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_sensitive_routing_retains_requires_authority_after_staff_override():
    """When the underlying model prediction is a sensitive intent (e.g. payment_issue, cancel_order,
    request_refund, return_product), staff override to a non-sensitive intent (e.g. track_order)
    must STILL retain 'requires_authority' in routing reason_codes.
    """
    model = MockModel(intent="request_refund", confidence=0.95, margin=0.80)
    engine = make_engine(model=model)

    req = {
        "message": "I want a refund for my order.",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "intent_override": "track_order",  # Non-sensitive override
    }
    analysis = engine.analyse(req)
    assert "requires_authority" in analysis["routing"]["reason_codes"]


def test_sensitive_keywords_retain_requires_authority_after_staff_override():
    """When the user message mentions sensitive keywords ('unauthorized payment', 'chargeback'),
    staff override must still retain 'requires_authority'.
    """
    model = MockModel(intent="delivery_time", confidence=0.90, margin=0.75)
    engine = make_engine(model=model)

    req = {
        "message": "There is an unauthorized payment on my credit card.",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "intent_override": "shipping_costs",
    }
    analysis = engine.analyse(req)
    assert "requires_authority" in analysis["routing"]["reason_codes"]


def test_system_prompt_instructs_against_overgeneralization_and_duplicate_advice():
    """Verify that SYSTEM_PROMPT in gemini.py includes explicit instructions against
    cosmetics overgeneralization and against offering duplicate-charge advice on unauthorized charges.
    """
    assert "unsealed" in SYSTEM_PROMPT.lower() or "overgeneralize" in SYSTEM_PROMPT.lower()
    assert "duplicate" in SYSTEM_PROMPT.lower() or "chargeback" in SYSTEM_PROMPT.lower()


def test_unauthorized_payment_retrieval_excludes_pol_pay_004():
    """When a customer asks about unauthorized payment or chargeback, the active retriever
    must NOT return POL-PAY-004 (which only covers duplicate charges).
    """
    import json
    from pathlib import Path
    from pipeline.evaluation.mock_dependencies import MockPolicyEncoder
    release = json.loads(Path("apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
    adapter = RetrievalAdapter(encoder=MockPolicyEncoder(), allowed_document_versions=allowed, relevance_threshold=0.35)

    res = adapter.retrieve("I will initiate a chargeback for this unauthorized transaction.", "payment_issue")
    doc_ids = [d["document_id"] for d in res.get("evidence", [])]
    assert "POL-PAY-004" not in doc_ids


def test_duplicate_charge_query_still_retrieves_pol_pay_004():
    """When a customer legitimately asks about duplicate deduction / charged twice,
    POL-PAY-004 is eligible and not excluded.
    """
    import json
    from pathlib import Path
    from pipeline.evaluation.mock_dependencies import MockPolicyEncoder
    release = json.loads(Path("apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
    adapter = RetrievalAdapter(encoder=MockPolicyEncoder(), allowed_document_versions=allowed, relevance_threshold=0.20)

    res = adapter.retrieve("duplicate charge deduction transaction recorded charged twice", "payment_issue")
    assert res["status"] == "success"
    doc_ids = [d["document_id"] for d in res["evidence"]]
    assert "POL-PAY-004" in doc_ids


def test_expired_policy_returns_no_match():
    """Evaluating a query at a date past valid_to (e.g. 2027) returns no_match and empty evidence."""
    import json
    from pathlib import Path
    from pipeline.evaluation.mock_dependencies import MockPolicyEncoder
    release = json.loads(Path("apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
    adapter = RetrievalAdapter(encoder=MockPolicyEncoder(), allowed_document_versions=allowed, relevance_threshold=0.35)

    future_time = datetime(2027, 3, 1, tzinfo=timezone.utc)
    res = adapter.retrieve("What is your return policy?", "return_policy", current_time=future_time)
    assert res["status"] == "no_match"
    assert res["evidence"] == []


def test_conflicting_policy_sources_flags_conflicting_sources():
    """When retriever detects conflicting policy documents, Engine.analyse flags conflicting_sources
    and recommends abstain.
    """
    retriever = MockRetriever(has_conflict=True)
    engine = make_engine(retriever=retriever)

    req = {
        "message": "What is the return window?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    analysis = engine.analyse(req)
    assert analysis["routing"]["recommendation"] == "abstain"
    assert "conflicting_sources" in analysis["routing"]["reason_codes"]
    assert any("conflicting" in w.lower() for w in analysis["warnings"])


def test_unanswerable_human_agent_escalates():
    """Queries requesting a human agent route to escalation without generating a draft."""
    model = MockModel(intent="human_agent", confidence=0.98, margin=0.90)
    engine = make_engine(model=model)

    req = {
        "message": "Transfer me to a live human representative please.",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    analysis = engine.analyse(req)
    assert analysis["routing"]["recommendation"] == "escalate"
    assert "human_agent_requested" in analysis["routing"]["reason_codes"]

    draft_res = engine.draft(req)
    assert draft_res["status"] == "escalation_recommended"
    assert "human_agent_requested" in draft_res["reason_codes"]


def test_unanswerable_out_of_scope_abstains():
    """Queries for out-of-scope intents recommend abstain."""
    model = MockModel(intent="recover_password", confidence=0.95, margin=0.85)
    engine = make_engine(model=model)

    req = {
        "message": "How do I reset my account password?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    analysis = engine.analyse(req)
    assert analysis["routing"]["recommendation"] == "abstain"
    assert "out_of_scope_intent" in analysis["routing"]["reason_codes"]

    draft_res = engine.draft(req)
    assert draft_res["status"] == "abstained"


def test_llm_usage_and_metadata_preserved_when_grounding_fails():
    """When LLM generation succeeds but grounding validation fails,
    Engine must retain complete llm_usage and llm_metadata rather than dropping them.
    """
    evidence = [{
        "document_id": "POL-RET-003",
        "version": "2.0",
        "title": "Restricted Return Categories",
        "excerpt": "Cosmetics with unsealed protective packaging cannot be returned...",
        "score": 0.85,
    }]
    sources = [{
        "source_id": "S1",
        "source_type": "policy",
        "document_id": "POL-RET-003",
        "version": "2.0",
        "excerpt": evidence[0]["excerpt"],
    }]

    class UsageReportingLLM:
        def generate(self, message, intent, evidence, business_context=None):
            return {
                "body": "Cosmetics cannot be returned at all. [S1]",  # Will fail overgeneralization check
                "input_snapshot": {"sources": sources},
                "is_clarification": False,
                "latency_seconds": 0.35,
                "provider": "google_ai_studio",
                "model": "gemini-3.1-flash-lite",
                "model_version": "gemini-3.1-flash-lite-001",
                "prompt_version": "grounded-v2",
                "usage": {
                    "promptTokenCount": 250,
                    "candidatesTokenCount": 40,
                    "totalTokenCount": 290,
                    "thoughtsTokenCount": 15,
                },
            }

    engine = make_engine(
        retriever=MockRetriever(evidence=evidence),
        llm=UsageReportingLLM(),
    )

    req = {
        "message": "Can I return a cosmetic lotion I purchased?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    res = engine.draft(req)
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]

    # Usage and latency must be retained despite grounding failure
    assert "llm_usage" in res
    assert res["llm_usage"]["input_tokens"] == 250
    assert res["llm_usage"]["output_tokens"] == 40
    assert res["llm_usage"]["total_tokens"] == 290
    assert res["llm_usage"]["thought_tokens"] == 15
    assert res["step_latency_ms"].get("llm") == 350
    assert res.get("llm_metadata", {}).get("provider") == "google_ai_studio"
    assert res.get("llm_metadata", {}).get("model") == "gemini-3.1-flash-lite"


def test_llm_usage_does_not_add_fake_zero_thought_tokens():
    """When thoughtsTokenCount is not present in raw usage, thought_tokens must be omitted,
    never fabricated as 0.
    """
    evidence = [{
        "document_id": "POL-RET-001",
        "version": "2.0",
        "title": "Standard Return Policy",
        "excerpt": "Return within 30 days.",
        "score": 0.90,
    }]
    sources = [{
        "source_id": "S1",
        "source_type": "policy",
        "document_id": "POL-RET-001",
        "version": "2.0",
        "excerpt": evidence[0]["excerpt"],
    }]

    class NoThoughtLLM:
        def generate(self, message, intent, evidence, business_context=None):
            return {
                "body": "Return within 30 days. [S1]",
                "input_snapshot": {"sources": sources},
                "is_clarification": False,
                "latency_seconds": 0.20,
                "provider": "google_ai_studio",
                "model": "gemini-3.1-flash-lite",
                "usage": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 20,
                    "totalTokenCount": 120,
                    # No thoughtsTokenCount
                },
            }

    engine = make_engine(
        retriever=MockRetriever(evidence=evidence),
        llm=NoThoughtLLM(),
    )

    req = {
        "message": "What is the return window?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    res = engine.draft(req)
    assert res["status"] == "draft_ready"
    assert "llm_usage" in res
    assert res["llm_usage"]["input_tokens"] == 100
    assert res["llm_usage"]["output_tokens"] == 20
    assert res["llm_usage"]["total_tokens"] == 120
    assert "thought_tokens" not in res["llm_usage"]  # Must not invent fake 0!


