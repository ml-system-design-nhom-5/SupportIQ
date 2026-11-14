from datetime import datetime, timezone
from types import SimpleNamespace
import pytest

from apps.ai_service.engine import Engine


class MockModel:
    def __init__(self, intent="track_order", confidence=0.95, margin=0.85, score_kind="uncalibrated_softmax", model_mode="trained", verified=True):
        self.intent = intent
        self.confidence = confidence
        self.margin = margin
        self.score_kind = score_kind
        self.model_mode = model_mode
        self.verified = verified

    def predict(self, text):
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "margin": self.margin,
            "score_kind": self.score_kind,
            "model_mode": self.model_mode,
            "verified": self.verified,
            "model_version": "v1.0.0",
            "top_k": [
                {"intent": self.intent, "probability": self.confidence},
                {"intent": "product_information", "probability": 0.03},
            ]
        }


class MockRetriever:
    def __init__(self, evidence=None, has_conflict=False):
        self.evidence = evidence if evidence is not None else [
            {"document_id": "policy-shipping-v1", "version": "1", "title": "Shipping Policy", "excerpt": "Delivery takes 3 to 5 business days.", "score": 0.88}
        ]
        self.has_conflict = has_conflict
        self.eligible_versions = [
            SimpleNamespace(
                doc_id=item["document_id"],
                version=item["version"],
                title=item["title"],
                content=item["excerpt"],
                metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to=None)
            )
            for item in self.evidence
        ]

    def retrieve(self, message, intent, role="agent", current_time=None):
        return {
            "status": "success",
            "evidence": self.evidence,
            "has_conflict": self.has_conflict,
        }


class MockLLM:
    def __init__(self, body="Standard delivery takes 3 to 5 business days. [S1]", sources=None, is_clarification=False, error=None):
        self.body = body
        self.sources = sources or [
            {"source_id": "S1", "source_type": "policy", "document_id": "policy-shipping-v1", "version": "1", "excerpt": "Delivery takes 3 to 5 business days."}
        ]
        self.is_clarification = is_clarification
        self.error = error

    def generate(self, message, intent, evidence, business_context=None):
        if self.error:
            raise self.error
        return {
            "body": self.body,
            "input_snapshot": {"sources": self.sources},
            "is_clarification": self.is_clarification,
            "latency_seconds": 0.12,
            "usage": {"promptTokenCount": 150, "candidatesTokenCount": 45}
        }


def make_engine(model=None, retriever=None, llm=None):
    policy = {
        "supported_12_intents": [
            "track_order", "cancel_order", "delivery_time", "delivery_issue",
            "shipping_costs", "return_policy", "return_product", "refund_policy",
            "request_refund", "refund_status", "payment_issue", "human_agent"
        ],
        "sensitive_action_intents": ["cancel_order", "request_refund"],
        "default_confidence_threshold": 0.70,
        "default_margin_threshold": 0.10,
        "confidence_thresholds": {},
        "margin_thresholds": {},
    }
    versions = {
        "release_id": "rel-test-001",
        "model_version": "v1.0.0",
        "model_mode": "trained",
        "verified": True,
        "kb_version": "kb-v2",
        "prompt_version": "grounded-v2",
        "routing_version": "policy-v2",
        "index_version": "bge-test"
    }
    return Engine(
        model=model or MockModel(),
        retriever=retriever or MockRetriever(),
        llm=llm or MockLLM(),
        versions=versions,
        policy=policy,
    )


def make_request(**kwargs):
    req = {
        "message": "Where is my order #12345?",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "order_context": {"order_status": "shipped"},
    }
    req.update(kwargs)
    return req


def test_short_paragraph_with_factual_commitment_requires_citation():
    """Short paragraphs (<=40 chars) stating financial or duration claims MUST have citations."""
    llm = MockLLM(body="We will refund $50.")
    engine = make_engine(llm=llm)

    res = engine.draft(make_request())
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_short_paragraph_with_return_window_requires_citation():
    """Short paragraph asserting return window without citation must fail grounding."""
    llm = MockLLM(body="Return window is 14 days.")
    engine = make_engine(llm=llm)

    res = engine.draft(make_request())
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_harmless_greeting_without_citation_allowed_when_grounded():
    """Short polite greetings (e.g. 'Hello [NAME_1],') without factual claims are allowed."""
    llm = MockLLM(body="Hello [NAME_1],\n\nStandard delivery takes 3 to 5 business days. [S1]")
    engine = make_engine(llm=llm)

    req = make_request(message="Hello [NAME_1], where is my order?")
    res = engine.draft(req)
    assert res["status"] == "draft_ready"
    assert len(res["draft"]["segments"]) == 2
    assert res["draft"]["segments"][0]["text"] == "Hello [NAME_1],"
    assert res["draft"]["segments"][0]["citation_ids"] == []
    assert res["draft"]["segments"][1]["citation_ids"] == ["S1"]


def test_polite_topic_framing_allowed_and_adversarial_framing_rejected_in_engine():
    """Non-factual polite framing >40 chars passes alongside cited policy while uncited claims fail."""
    ok_llm = MockLLM(
        body=(
            "Thank you for reaching out about your order.\n\n"
            "Standard delivery takes 3 to 5 business days. [S1]\n\n"
            "Please let us know if you have questions about this policy."
        )
    )
    ok_res = make_engine(llm=ok_llm).draft(make_request())
    assert ok_res["status"] == "draft_ready"
    assert [seg["citation_ids"] for seg in ok_res["draft"]["segments"]] == [[], ["S1"], []]

    bad_llm = MockLLM(
        body=(
            "We apologize, your order will arrive tomorrow.\n\n"
            "Standard delivery takes 3 to 5 business days. [S1]"
        )
    )
    bad_res = make_engine(llm=bad_llm).draft(make_request())
    assert bad_res["status"] == "llm_unavailable"
    assert "grounding_failed" in bad_res["reason_codes"]


@pytest.mark.parametrize("body", [
    "Shipping is free.\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "Your order is cancelled.\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "We approved your return.\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "Hello, you get a free gift!\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "You are eligible.\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "No charge applies.\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "It will arrive tomorrow.\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "Shipping is free.",
    "Could you provide your order ID?\n\nStandard delivery takes 3 to 5 business days. [S1]",
    "Standard delivery takes 3 to 5 business days [S1]. Shipping is free.",
    "Shipping is free. Standard delivery takes 3 to 5 business days [S1].",
    "Standard delivery takes 3 to 5 business days [S1]; Shipping is free.",
    "Shipping is free; Standard delivery takes 3 to 5 business days [S1].",
    "Standard delivery takes 3 to 5 business days [S1].\nShipping is free.",
    "Standard delivery takes 3 to 5 business days [S1].Shipping is free.",
    "Standard delivery takes 7 business days [S1].",
    "We have refunded your order [S1].",
    "Standard delivery takes 3 to 5 business days [s1].",
    "Standard delivery takes 3 to 5 business days [S1, S2].",
])
def test_engine_direct_stub_rejects_short_uncited_claims_and_mixed_citation_bypasses(body):
    """Engine.draft must reject <=40 char factual claims and uncited claims mixed into [S1] paragraphs."""
    res = make_engine(llm=MockLLM(body=body)).draft(make_request())
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_engine_direct_stub_rejects_clarification_with_factual_question_and_source_tampering():
    """Clarification flag must not pass factual questions, and fabricated/unowned sources must fail closed."""
    clarify_bad = MockLLM(
        body="Is shipping free?\n\nStandard delivery takes 3 to 5 business days. [S1]",
        is_clarification=True,
    )
    res_q = make_engine(llm=clarify_bad).draft(make_request())
    assert res_q["status"] == "llm_unavailable"
    assert "grounding_failed" in res_q["reason_codes"]

    class CitationsTamperLLM(MockLLM):
        def generate(self, message, intent, evidence, business_context=None):
            payload = super().generate(message, intent, evidence, business_context=business_context)
            payload["citations"] = ["S1"]
            return payload

    res_list = make_engine(
        llm=CitationsTamperLLM(body="Standard delivery takes 3 to 5 business days [S1]. Shipping is free.")
    ).draft(make_request())
    assert res_list["status"] == "llm_unavailable"
    assert "grounding_failed" in res_list["reason_codes"]

    class MismatchedCitationDocLLM(MockLLM):
        def generate(self, message, intent, evidence, business_context=None):
            payload = super().generate(message, intent, evidence, business_context=business_context)
            payload["citations"] = [{"source_id": "S1", "document_id": "POL-FORGED", "version": "1"}]
            return payload

    res_forged = make_engine(
        llm=MismatchedCitationDocLLM(body="Standard delivery takes 3 to 5 business days. [S1]")
    ).draft(make_request())
    assert res_forged["status"] == "llm_unavailable"
    assert "grounding_failed" in res_forged["reason_codes"]

    bad_type_sources = [
        {"source_id": "S1", "source_type": "policy", "document_id": "policy-shipping-v1", "version": "1", "excerpt": "Delivery takes 3 to 5 business days."},
        {"source_id": "S2", "source_type": "arbitrary_source", "document_id": "order-1", "version": "1", "excerpt": "order_status: shipped"},
    ]
    res_type = make_engine(
        llm=MockLLM(body="Delivery takes 3 to 5 business days [S1]. Order is shipped [S2].", sources=bad_type_sources)
    ).draft(make_request())
    assert res_type["status"] == "llm_unavailable"
    assert "grounding_failed" in res_type["reason_codes"]


def test_engine_direct_stub_accepts_mixed_policy_and_order_facts_with_polite_framing():
    """Engine.draft preserves valid polite framing alongside mixed S1 policy and S2 order_facts."""
    from apps.core_backend.llm.gemini import build_grounded_sources

    order_ctx = {
        "order_status": "shipped",
        "shipment_status": "delayed",
        "shipping_cost": {"amount_minor": 0, "currency": "VND"},
        "refund_amount": {"amount_minor": 499000, "currency": "VND"},
    }
    retriever = MockRetriever()
    sources = build_grounded_sources(retriever.evidence, order_ctx)
    body = (
        "Thank you for reaching out about your order.\n\n"
        "Standard delivery takes 3 to 5 business days. [S1]\n\n"
        "Your shipment is delayed with 0 VND shipping and 499,000 VND refund [S2].\n\n"
        "Please let us know if you have questions about this policy."
    )
    req = make_request(order_context=order_ctx)
    res = make_engine(retriever=retriever, llm=MockLLM(body=body, sources=sources)).draft(req)
    assert res["status"] == "draft_ready"
    assert set(res["draft"]["citations"][1]["fields"]) >= {"shipment_status", "shipping_cost", "refund_amount"}
    assert [seg["citation_ids"] for seg in res["draft"]["segments"]] == [[], ["S1"], ["S2"], []]


@pytest.mark.parametrize("body,forged_sources", [
    (
        "Shipping is free forever. [S1]",
        [{"source_id": "S1", "source_type": "policy", "document_id": "POL-FABRICATED", "version": "9.9", "excerpt": "Shipping is free forever."}],
    ),
    (
        "Delivery takes 3 to 5 business days. [S1]",
        [{"source_id": "S1", "source_type": "policy", "document_id": "policy-shipping-v1", "version": "9.9", "excerpt": "Delivery takes 3 to 5 business days."}],
    ),
    (
        "Shipping is always free for everyone. [S1]",
        [{"source_id": "S1", "source_type": "policy", "document_id": "policy-shipping-v1", "version": "1", "excerpt": "Shipping is always free for everyone."}],
    ),
    (
        "Delivery takes 3 to 5 business days. [S1]",
        [{"source_id": "S1", "source_type": "order_facts", "document_id": "policy-shipping-v1", "version": "1", "excerpt": "Delivery takes 3 to 5 business days."}],
    ),
])
def test_engine_draft_rejects_forged_input_snapshot_against_authoritative_sources(body, forged_sources):
    """Engine.draft must validate against authoritative retrieval/order sources, never LLM-reported snapshots."""
    class ForgedSnapshotLLM:
        def generate(self, message, intent, evidence, business_context=None):
            return {
                "body": body,
                "citations": [{"source_id": "S1", "document_id": forged_sources[0]["document_id"], "version": forged_sources[0]["version"]}],
                "input_snapshot": {"sources": forged_sources},
                "latency_seconds": 0.05,
                "usage": {},
            }

    res = make_engine(llm=ForgedSnapshotLLM()).draft(make_request())
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_engine_draft_rejects_conflicting_order_facts_snapshot_and_in_place_mutation():
    """Engine.draft must reject forged S2 order_facts contradicting request.order_context and resist in-place mutation."""
    order_ctx = {"order_status": "shipped", "refund_status": "pending"}
    req = make_request(order_context=order_ctx)

    class ConflictingOrderLLM:
        def generate(self, message, intent, evidence, business_context=None):
            evidence[0]["excerpt"] = "Shipping is completely free."
            if isinstance(business_context, dict):
                business_context["order_status"] = "Cancelled"
            return {
                "body": "Your order is cancelled [S2].",
                "citations": ["S2"],
                "input_snapshot": {
                    "sources": [
                        {"source_id": "S1", "source_type": "policy", "document_id": "policy-shipping-v1", "version": "1", "excerpt": "Delivery takes 3 to 5 business days."},
                        {"source_id": "S2", "source_type": "order_facts", "document_id": "ORDER-FACTS", "version": "facts", "excerpt": "Verified Order Details:\norder_status: Cancelled\nrefund_status: Refunded"},
                    ]
                },
                "latency_seconds": 0.05,
                "usage": {},
            }

    res = make_engine(llm=ConflictingOrderLLM()).draft(req)
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


@pytest.mark.parametrize("body", [
    "Your order is cancelled [S1].",
    "Your refund is approved [S1].",
    "Your return is approved [S1].",
    "Your refund is refunded [S1].",
    "Your return is processed [S1].",
    "Your order is credited [S1].",
    "Shipping is free.Delivery takes 3 to 5 business days [S1].",
    "Delivery takes 3 to 5 business days [S1], shipping is free.",
    "Shipping is free, delivery takes 3 to 5 business days [S1].",
    "Delivery takes 3 to 5 business days (shipping is free) [S1].",
    "Delivery takes 3 to 5 business days - shipping is free [S1].",
    "Shipping is free: delivery takes 3 to 5 business days [S1].",
])
def test_engine_draft_rejects_bare_passive_status_and_splice_bypasses(body):
    """Engine.draft must reject bare present-tense passive commitments, missing-space periods, and clause splices."""
    res = make_engine(llm=MockLLM(body=body)).draft(make_request())
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_short_clarification_without_citation_allowed():
    """Short clarification question asking for missing details alongside cited policy is allowed."""
    llm = MockLLM(
        body="Could you provide your order ID?\n\nStandard delivery takes 3 to 5 business days. [S1]",
        is_clarification=True,
    )
    engine = make_engine(llm=llm)

    res = engine.draft(make_request())
    assert res["status"] == "draft_ready"
    assert "missing_information" in res["reason_codes"]
    assert "clarification" in res["staff_note"].lower()
    assert len(res["draft"]["segments"]) == 2
    assert res["draft"]["segments"][0]["citation_ids"] == []
    assert res["draft"]["segments"][1]["citation_ids"] == ["S1"]


def test_missing_prediction_provenance_metadata_defaults_to_unknown_and_false():
    """When the underlying model prediction omits model_mode and verified,
    the gateway must default to 'unknown' and False, never inventing trusted provenance."""
    class BareModel:
        def predict(self, text):
            return {
                "intent": "track_order",
                "confidence": 0.95,
                "margin": 0.85,
                "score_kind": "uncalibrated_softmax",
                "model_version": "v1.0.0",
                "top_k": [{"intent": "track_order", "probability": 0.95}],
                # model_mode and verified are intentionally omitted
            }

    engine = make_engine(model=BareModel())
    analysis = engine.analyse(make_request())
    assert analysis["intent"]["model_mode"] == "unknown"
    assert analysis["intent"]["verified"] is False


def test_unsupported_citation_identifier_fails_grounding():
    """Referencing a source ID that does not exist in input_snapshot causes grounding failure."""
    llm = MockLLM(body="This is an ungrounded claim. [S99]")
    engine = make_engine(llm=llm)

    res = engine.draft(make_request())
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_missing_order_context_field_citation_fails_grounding():
    """Citing an order source when the required field is absent from order_context fails grounding."""
    sources = [
        {"source_id": "S1", "source_type": "policy", "document_id": "policy-shipping-v1", "version": "1", "excerpt": "Delivery takes 3 to 5 business days."},
        {"source_id": "S2", "source_type": "order", "document_id": "order-1", "version": "1", "excerpt": "Order details."},
    ]
    llm = MockLLM(body="Status is confirmed. [S2]", sources=sources)
    engine = make_engine(llm=llm)

    # Order context is empty
    req = make_request(order_context={})
    res = engine.draft(req)
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]


def test_no_valid_document_abstains_without_calling_llm():
    """When retriever finds no valid documents, abstain without generating draft."""
    class FailIfCalledLLM:
        def generate(self, *args, **kwargs):
            raise AssertionError("LLM must not be called when no valid document is retrieved")

    retriever = MockRetriever(evidence=[])
    engine = make_engine(retriever=retriever, llm=FailIfCalledLLM())

    analysis = engine.analyse(make_request())
    assert analysis["routing"]["recommendation"] == "abstain"
    assert "no_valid_document" in analysis["routing"]["reason_codes"]

    draft_res = engine.draft(make_request())
    assert draft_res["status"] == "abstained"
    assert "no_valid_document" in draft_res["reason_codes"]


def test_conflicting_sources_abstains_with_warning():
    """When retriever detects conflicting policy documents, abstain with explicit warning."""
    retriever = MockRetriever(has_conflict=True)
    engine = make_engine(retriever=retriever)

    analysis = engine.analyse(make_request())
    assert analysis["routing"]["recommendation"] == "abstain"
    assert "conflicting_sources" in analysis["routing"]["reason_codes"]
    assert any("conflicting" in w.lower() for w in analysis["warnings"])

    draft_res = engine.draft(make_request())
    assert draft_res["status"] == "abstained"
    assert "conflicting_sources" in draft_res["reason_codes"]


def test_sensitive_chargeback_keyword_triggers_requires_authority():
    """Keywords like 'chargeback' or 'lawsuit' must trigger requires_authority."""
    engine = make_engine()
    analysis = engine.analyse(make_request(message="I will initiate a chargeback if this is not resolved."))
    assert "requires_authority" in analysis["routing"]["reason_codes"]


def test_human_agent_intent_escalates():
    """human_agent intent must recommend escalation and not generate draft."""
    model = MockModel(intent="human_agent", confidence=0.98, margin=0.90)
    engine = make_engine(model=model)

    analysis = engine.analyse(make_request())
    assert analysis["routing"]["recommendation"] == "escalate"
    assert "human_agent_requested" in analysis["routing"]["reason_codes"]

    draft_res = engine.draft(make_request())
    assert draft_res["status"] == "escalation_recommended"
    assert "human_agent_requested" in draft_res["reason_codes"]


def test_out_of_scope_intent_abstains():
    """Intents outside the 12 supported product intents must abstain."""
    model = MockModel(intent="product_information", confidence=0.95, margin=0.80)
    engine = make_engine(model=model)

    analysis = engine.analyse(make_request())
    assert analysis["routing"]["recommendation"] == "abstain"
    assert "out_of_scope_intent" in analysis["routing"]["reason_codes"]

    draft_res = engine.draft(make_request())
    assert draft_res["status"] == "abstained"


def test_staff_override_provenance_never_masquerades_as_model_probability():
    """Staff override must record source='staff', score_kind='staff_choice',
    and model_mode='override' with verified=False."""
    engine = make_engine()
    req = make_request(intent_override="cancel_order")

    analysis = engine.analyse(req)
    intent_data = analysis["intent"]
    assert intent_data["label"] == "cancel_order"
    assert intent_data["source"] == "staff"
    assert intent_data["score_kind"] == "staff_choice"
    assert intent_data["model_mode"] == "override"
    assert intent_data["verified"] is False
    assert intent_data["probability"] == 1.0


def test_llm_timeout_handled_gracefully():
    """LLM timeouts should map to llm_unavailable and provide staff note."""
    class TimeoutError(Exception):
        code = "llm_timeout"

    llm = MockLLM(error=TimeoutError("Request timed out"))
    engine = make_engine(llm=llm)

    res = engine.draft(make_request())
    assert res["status"] == "llm_unavailable"
    assert res.get("failure_code") == "llm_timeout"
    assert "timed out" in res.get("staff_note", "").lower()
