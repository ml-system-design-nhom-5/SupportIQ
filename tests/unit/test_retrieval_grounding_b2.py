import json
from pathlib import Path
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
        self.calls = []

    def generate(self, message, intent, evidence, business_context=None):
        self.calls.append({"message": message, "intent": intent})
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
    assert res["status"] == "escalation_recommended"
    assert "requires_authority" in res["reason_codes"]


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
    """Flag propagation test: when retriever signals has_conflict=True, Engine.analyse
    propagates conflicting_sources into reason_codes and recommends abstain.
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


def test_contradictory_versioned_kb_fixture_detected_by_retrieval_adapter(tmp_path):
    """Real conflict detection test: when multiple active eligible documents share
    the same policy_key (e.g. contradictory return window rules), RetrievalAdapter detects has_conflict=True.
    """
    from apps.core_backend.retrieval.adapter import RetrievalAdapter

    kb_fixture = [
        {
            "document_id": "POL-RET-TEST-001",
            "version": "1.0",
            "title": "Standard Return Policy 30 Days",
            "content": "Customers can return items within 30 days of delivery.",
            "status": "approved",
            "approved_by": "qa-lead",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": None,
            "allowed_roles": ["agent"],
            "policy_key": "standard_return_window",
            "supported_intents": ["return_policy"],
            "answer_capabilities": ["return_window"],
        },
        {
            "document_id": "POL-RET-TEST-002",
            "version": "2.0",
            "title": "Standard Return Policy 14 Days Contradictory",
            "content": "Customers can return items within 14 days of delivery.",
            "status": "approved",
            "approved_by": "qa-lead",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": None,
            "allowed_roles": ["agent"],
            "policy_key": "standard_return_window",  # Same policy_key -> conflict!
            "supported_intents": ["return_policy"],
            "answer_capabilities": ["return_window"],
        },
    ]
    kb_file = tmp_path / "conflict_kb.json"
    kb_file.write_text(json.dumps(kb_fixture), encoding="utf-8")

    from pipeline.evaluation.mock_dependencies import MockPolicyEncoder

    adapter = RetrievalAdapter(
        kb_path=str(kb_file),
        allowed_document_versions={
            ("POL-RET-TEST-001", "1.0"),
            ("POL-RET-TEST-002", "2.0"),
        },
        encoder=MockPolicyEncoder(),
        relevance_threshold=0.0,
    )
    res = adapter.retrieve("What is the return window for items?", intent="return_policy")
    assert res["status"] == "success"
    assert len(res["evidence"]) == 2
    assert res["has_conflict"] is True


def test_all_five_gold_ood_queries_route_to_abstention_in_engine():
    """End-to-end Engine routing test: ALL 5 gold benchmark OOD queries route to abstention,
    verifying that no draft is generated and no false policy statements are served.
    """
    gold_path = Path(__file__).resolve().parents[2] / "data/benchmarks/app_retrieval_gold_v2.json"
    cases = json.loads(gold_path.read_text(encoding="utf-8"))
    ood_cases = [c for c in cases if c["slice"] == "ood"]
    assert len(ood_cases) == 5, f"Expected 5 OOD cases, got {len(ood_cases)}"

    for case in ood_cases:
        model = MockModel(intent=case["intent"], confidence=0.85, margin=0.70)
        mock_llm = MockLLM()
        engine = make_engine(model=model, llm=mock_llm)

        req = {
            "message": case["query"],
            "as_of": case["as_of"],
            "order_context": {},
        }
        res = engine.draft(req)
        assert res["status"] == "abstained", f"Case {case['id']} did not abstain: {res['status']}"
        assert "out_of_scope_intent" in res["reason_codes"], f"Case {case['id']} missing out_of_scope_intent"
        assert len(mock_llm.calls) == 0, f"Case {case['id']} unexpectedly called LLM"


def test_validate_preconditions_rejects_corrupted_manifest_or_hashes():
    """Verify that validate_preconditions raises explicit ValueError when manifest
    status, scope, gold hash, or KB/release hashes do not match.
    """
    from scripts.run_app_retrieval_benchmark import validate_preconditions

    manifest = {
        "status": "approved",
        "approval": {
            "approved": True,
            "approval_scope": "local_application_retrieval_evaluation",
        },
        "target_release": "release-v1",
        "sha256": "gold_hash_123",
        "provenance": {
            "kb_source_sha256": "kb_hash_123",
            "kb_release_sha256": "rel_hash_123",
        },
    }
    release_data = {"release": "release-v1"}

    # Valid case passes
    validate_preconditions(manifest, "gold_hash_123", "kb_hash_123", "rel_hash_123", release_data)

    # 1. Unapproved status
    bad_manifest = dict(manifest, status="pending")
    with pytest.raises(ValueError, match="status must be 'approved'"):
        validate_preconditions(bad_manifest, "gold_hash_123", "kb_hash_123", "rel_hash_123", release_data)

    # 2. Corrupted gold hash
    with pytest.raises(ValueError, match="Gold sha256 mismatch"):
        validate_preconditions(manifest, "corrupted_gold", "kb_hash_123", "rel_hash_123", release_data)

    # 3. Mismatched KB source hash
    with pytest.raises(ValueError, match="KB source sha256 mismatch"):
        validate_preconditions(manifest, "gold_hash_123", "wrong_kb", "rel_hash_123", release_data)

    # 4. Mismatched release hash
    with pytest.raises(ValueError, match="KB release sha256 mismatch"):
        validate_preconditions(manifest, "gold_hash_123", "kb_hash_123", "wrong_rel", release_data)


def test_llm_usage_does_not_synthesize_complete_total_when_total_token_count_absent():
    """When totalTokenCount is absent from provider raw usage, Engine does not synthesize
    it as total_tokens, preserving total_tokens_partial or leaving total_tokens unknown.
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

    class NoTotalLLM:
        def generate(self, message, intent, evidence, business_context=None):
            return {
                "body": "Return within 30 days. [S1]",
                "input_snapshot": {"sources": sources},
                "is_clarification": False,
                "latency_seconds": 0.20,
                "provider": "google_ai_studio",
                "model": "gemini-3.1-flash-lite",
                "usage": {
                    "promptTokenCount": 150,
                    "candidatesTokenCount": 35,
                    # No totalTokenCount!
                },
            }

    engine = make_engine(
        retriever=MockRetriever(evidence=evidence),
        llm=NoTotalLLM(),
    )
    req = {
        "message": "What is the return window?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    res = engine.draft(req)
    assert res["status"] == "draft_ready"
    assert "total_tokens" not in res["llm_usage"]  # Must not present synthesized sum as complete total!
    assert res["llm_usage"]["total_tokens_partial"] == 185


def test_gemini_client_and_engine_preserve_usage_on_insufficient_evidence():
    """When the provider returns answerable=false, GeminiDraftClient attaches usage/metadata
    to LLMError, and Engine.draft preserves llm_usage and llm_metadata on the failure path.
    """
    from apps.core_backend.llm.gemini import LLMError

    class RaisingLLM:
        def generate(self, message, intent, evidence, business_context=None):
            raise LLMError(
                "llm_insufficient_evidence",
                usage={"promptTokenCount": 200, "candidatesTokenCount": 25, "totalTokenCount": 225},
                metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                latency_seconds=0.42,
            )

    evidence = [{
        "document_id": "POL-REFUND-001",
        "version": "1.0",
        "title": "Refund Policy",
        "excerpt": "Refund rules...",
        "score": 0.90,
    }]
    engine = make_engine(retriever=MockRetriever(evidence=evidence), llm=RaisingLLM())
    req = {
        "message": "What is your refund policy?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {},
    }
    res = engine.draft(req)
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]
    assert res["failure_code"] == "llm_insufficient_evidence"
    assert res["llm_usage"]["input_tokens"] == 200
    assert res["llm_usage"]["output_tokens"] == 25
    assert res["llm_usage"]["total_tokens"] == 225
    assert res["llm_metadata"]["provider"] == "google_ai_studio"
    assert res["step_latency_ms"]["llm"] == 420


def test_jobs_store_persists_llm_metadata_additively():
    """Verify that SuggestionWorker.store persists llm_metadata into suggestion payload
    alongside llm_usage.
    """
    from apps.backend.tickets.jobs import SuggestionWorker
    from apps.backend.platform.models import Suggestion, Ticket, SuggestionJob
    from unittest.mock import MagicMock
    from contextlib import contextmanager

    session = MagicMock()
    ticket = MagicMock(spec=Ticket)
    ticket.ticket_id = "tick-123"
    ticket.current_suggestion_id = "sugg-123"

    job = MagicMock(spec=SuggestionJob)
    job.lease_token = "tok-abc"
    job.lease_until = None

    suggestion = MagicMock(spec=Suggestion)
    suggestion.ticket_id = "tick-123"
    suggestion.payload = {"analysis_status": "ready", "draft_status": "pending", "trace_id": "tr-123"}

    session.get.side_effect = lambda model, ident: suggestion if model is Suggestion else None
    session.scalar.side_effect = lambda query: ticket if "ticket" in str(query).lower() else job

    @contextmanager
    def mock_tx():
        yield session

    mock_db = MagicMock()
    mock_db.transaction = mock_tx

    worker = SuggestionWorker(database=mock_db, settings=MagicMock())

    draft_result = {
        "status": "draft_ready",
        "reason_codes": [],
        "draft": {"reply": "Here is your answer"},
        "analysis": {
            "versions": {"model_version": "v1.0"},
            "routing": {"reason_codes": []},
        },
        "llm_usage": {"input_tokens": 120, "output_tokens": 30},
        "llm_metadata": {
            "provider": "google_ai_studio",
            "model": "gemini-3.1-flash-lite",
            "model_version": "gemini-3.1-flash-lite-001",
            "prompt_version": "grounded-v2",
        },
    }

    worker.store("sugg-123", "tok-abc", "draft", draft_result, 150)

    payload = suggestion.payload
    assert payload["llm_usage"] == {"input_tokens": 120, "output_tokens": 30}
    assert payload["llm_metadata"] == {
        "provider": "google_ai_studio",
        "model": "gemini-3.1-flash-lite",
        "model_version": "gemini-3.1-flash-lite-001",
        "prompt_version": "grounded-v2",
    }


