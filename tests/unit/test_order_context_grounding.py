"""Focused TDD regression tests for order_context forwarding, type safety, and order_facts citations."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from apps.ai_service.engine import Engine
from apps.ai_service.main import SuggestionRequest
from apps.backend.tickets.jobs import SuggestionWorker
from apps.backend.tickets.service import order_context as build_backend_order_context
from apps.core_backend.llm.gemini import GeminiDraftClient, build_grounded_sources, prepare_llm_input
from scripts.collect_final_acceptance_evidence import AcceptanceEvidenceCollector


def _shipping_policy() -> dict:
    excerpt = "Orders ship within 1-2 business days. Delayed parcels qualify for tracking checks [POL-SHIP-001]."
    return {
        "source_type": "policy",
        "document_id": "POL-SHIP-001",
        "version": "1.0",
        "title": "Shipping Policy",
        "excerpt": excerpt,
        "content_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "score": 0.92,
    }


def _make_stub_gemini(answer: str, citations: list[str], captured_bodies: list[str] | None = None) -> GeminiDraftClient:
    def handler(req: httpx.Request) -> httpx.Response:
        if captured_bodies is not None:
            captured_bodies.append(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-3.5-flash-lite",
                "usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 24, "totalTokenCount": 104},
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "answerable": True,
                                            "answer": answer,
                                            "citations": citations,
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ],
            },
        )

    return GeminiDraftClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _make_engine(llm) -> Engine:
    policy_doc = _shipping_policy()
    model = SimpleNamespace(
        predict=lambda _text: {
            "intent": "track_order",
            "confidence": 0.96,
            "margin": 0.88,
            "score_kind": "calibrated_probability",
            "model_mode": "trained",
            "verified": True,
            "model_version": "v1.0.0",
            "top_k": [{"intent": "track_order", "probability": 0.96}, {"intent": "delivery_issue", "probability": 0.02}],
        }
    )
    retriever = SimpleNamespace(
        eligible_versions=[
            SimpleNamespace(
                doc_id=policy_doc["document_id"],
                version=policy_doc["version"],
                title=policy_doc["title"],
                content=policy_doc["excerpt"],
                metadata=SimpleNamespace(valid_from="2026-01-01T00:00:00Z", valid_to=None),
            )
        ],
        retrieve=lambda *a, **kw: {"status": "success", "evidence": [policy_doc], "has_conflict": False},
    )
    policy = {
        "supported_12_intents": ["track_order", "delivery_issue", "shipping_costs", "refund_status", "return_policy", "human_agent"],
        "sensitive_action_intents": ["cancel_order", "request_refund"],
        "default_confidence_threshold": 0.70,
        "default_margin_threshold": 0.10,
        "confidence_thresholds": {},
        "margin_thresholds": {},
    }
    return Engine(
        model=model,
        retriever=retriever,
        llm=llm,
        versions={"release_id": "rel-test", "model_version": "v1.0.0"},
        policy=policy,
    )


def test_six_field_backend_order_context_not_truncated_and_formats_zero_money():
    """All 6 backend order_context fields including 0 VND must reach S2 and prompt order_facts."""
    fake_order = SimpleNamespace(
        payload={
            "order_id": "ORD-8899",
            "customer_id": "cust-secret",
            "customer_name": "Tran Van Secret",
            "order_status": "shipped",
            "order_total": {"amount_minor": 1402000, "currency": "VND"},
            "shipping_cost": {"amount_minor": 0, "currency": "VND"},
            "shipment": {"shipment_status": "delayed", "tracking_code": "TRK-999"},
            "refund": {
                "refund_status": "requested",
                "refund_amount": {"amount_minor": 499000, "currency": "VND"},
            },
        }
    )
    ctx = build_backend_order_context(fake_order)
    snap = prepare_llm_input("Where is my delayed parcel?", "track_order", [_shipping_policy()], ctx)
    prompt_obj = json.loads(snap["prompt"])

    assert set(prompt_obj["order_facts"].keys()) == {
        "order_status",
        "order_total",
        "shipping_cost",
        "shipment_status",
        "refund_status",
        "refund_amount",
    }
    assert prompt_obj["order_facts"]["order_status"] == "shipped"
    assert prompt_obj["order_facts"]["shipment_status"] == "delayed"
    assert prompt_obj["order_facts"]["order_total"] == "1,402,000 VND"
    assert prompt_obj["order_facts"]["shipping_cost"] == "0 VND"
    assert prompt_obj["order_facts"]["refund_amount"] == "499,000 VND"

    s2_prompt = prompt_obj["sources"][1]
    assert s2_prompt["source_id"] == "S2"
    assert s2_prompt["document_id"] == "ORDER-FACTS"
    for expected in ("shipment_status: delayed", "order_total: 1,402,000 VND", "shipping_cost: 0 VND", "refund_amount: 499,000 VND"):
        assert expected in s2_prompt["excerpt"]
        assert expected in snap["sources"][1]["excerpt"]


def test_ten_field_allowlist_type_safety_and_nested_money_pii_filtering():
    """Ten allowed fields preserve valid zero/decimal money and dates while dropping invalid/PII nested data."""
    payload = {
        "order_status": "shipped",
        "placed_at": "2026-10-19T07:00:00Z",
        "order_total": {"amount_minor": 10000000, "currency": "VND"},
        "shipping_cost": {"amount_minor": 0, "currency": "USD"},
        "shipment_status": "delayed",
        "estimated_delivery_at": "2026-10-25",
        "delivered_at": None,  # Truly absent optional timestamp must be omitted
        "refund_status": "approved",
        "refund_amount": {"amount_minor": 1999, "currency": "USD"},
        "refund_requested_at": "2026-10-20T09:15:00Z",
        "order_id": "ORD-LEAK-1",
        "customer_id": "cust-leak-1",
        "customer_name": "Nguyen Van Leak",
        "email": "leak@example.com",
        "shipping_address": "123 Secret St",
    }
    snap = prepare_llm_input("Check my order", "track_order", [_shipping_policy()], payload)
    prompt_obj = json.loads(snap["prompt"])
    facts = prompt_obj["order_facts"]

    assert "delivered_at" not in facts
    assert facts["placed_at"] == "2026-10-19T07:00:00Z"
    assert facts["estimated_delivery_at"] == "2026-10-25"
    assert facts["refund_requested_at"] == "2026-10-20T09:15:00Z"
    assert facts["order_total"] == "10,000,000 VND"
    assert facts["shipping_cost"] == "0.00 USD"
    assert facts["refund_amount"] == "19.99 USD"

    for secret in ("ORD-LEAK-1", "cust-leak-1", "Nguyen Van Leak", "leak@example.com", "123 Secret St"):
        assert secret not in snap["prompt"]

    # Poisoned nested / invalid field payloads must NEVER leak or fabricate facts
    poisoned = {
        "order_status": {"nested": "Secret"},
        "placed_at": "Call 0912345678 Nguyen Van A",
        "order_total": {"amount_minor": 50000, "currency": "VND", "customer_id": "cust-secret"},
        "shipping_cost": {"amount_minor": True, "currency": "VND"},
        "refund_amount": {"amount_minor": -50, "currency": "VND"},
        "shipment_status": "delayed",
    }
    poison_snap = prepare_llm_input("Check", "track_order", [_shipping_policy()], poisoned)
    poison_facts = json.loads(poison_snap["prompt"])["order_facts"]
    assert poison_facts == {"shipment_status": "delayed"}
    assert "cust-secret" not in poison_snap["prompt"]
    assert "0912345678" not in poison_snap["prompt"]


@pytest.mark.parametrize(
    "bad_context",
    [
        {"order_id": "ORD-1"},
        {"order_total": {"amount_minor": 500, "currency": "VND", "extra": "leak"}},
        {"shipping_cost": {"amount_minor": True, "currency": "VND"}},
        {"refund_amount": {"amount_minor": -1, "currency": "VND"}},
        {"placed_at": "not-a-date Call 0912345678"},
        {"order_status": {"bad": "dict"}},
    ],
)
def test_suggestion_request_rejects_invalid_or_leaky_order_context(bad_context):
    with pytest.raises(ValidationError):
        SuggestionRequest(
            message="Where is my order?",
            order_context=bad_context,
            as_of="2026-10-20T00:00:00Z",
        )


def test_engine_draft_six_fields_source_level_citation_not_arbitrarily_order_status():
    """Multi-field S2 citation must reflect supplied fields honestly without inventing sentence field mapping or order_status."""
    captured: list[str] = []
    llm = _make_stub_gemini(
        answer=(
            "Orders ship within 1-2 business days [S1].\n\n"
            "Your shipment is delayed with 0 VND shipping and 499,000 VND refund [S2]."
        ),
        citations=["S1", "S2"],
        captured_bodies=captured,
    )
    try:
        eng = _make_engine(llm)
        req = {
            "message": "My parcel is delayed, how much was shipping and refund?",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "order_context": {
                "order_status": "shipped",
                "order_total": {"amount_minor": 1402000, "currency": "VND"},
                "shipping_cost": {"amount_minor": 0, "currency": "VND"},
                "shipment_status": "delayed",
                "refund_status": "requested",
                "refund_amount": {"amount_minor": 499000, "currency": "VND"},
            },
        }
        res = eng.draft(req)
    finally:
        llm.close()

    assert res["status"] == "draft_ready"
    assert len(captured) == 1
    wire = json.loads(json.loads(captured[0])["contents"][0]["parts"][0]["text"])
    assert "0 VND" in wire["sources"][1]["excerpt"]
    assert "shipment_status: delayed" in wire["sources"][1]["excerpt"]

    cits = {c["citation_id"]: c for c in res["draft"]["citations"]}
    assert set(cits.keys()) == {"S1", "S2"}
    assert cits["S1"]["source_type"] == "kb_document"
    assert cits["S2"] == {
        "citation_id": "S2",
        "source_type": "order_context",
        "fields": [
            "order_status",
            "order_total",
            "shipping_cost",
            "shipment_status",
            "refund_status",
            "refund_amount",
        ],
    }
    assert res["draft"]["segments"][0]["citation_ids"] == ["S1"]
    assert res["draft"]["segments"][1]["citation_ids"] == ["S2"]


def test_engine_draft_succeeds_without_order_status_or_refund_status():
    """New allowed fields (shipment_status, placed_at, zero shipping, refund_amount) work when order_status/refund_status are absent."""
    llm = _make_stub_gemini(
        answer="Placed on 2026-10-19 with 0 VND shipping, your delayed parcel has a 499,000 VND refund [S2].",
        citations=["S2"],
    )
    try:
        eng = _make_engine(llm)
        res = eng.draft(
            {
                "message": "When did I place my order and what is the refund amount?",
                "as_of": datetime.now(timezone.utc).isoformat(),
                "order_context": {
                    "placed_at": "2026-10-19T07:00:00Z",
                    "shipping_cost": {"amount_minor": 0, "currency": "VND"},
                    "shipment_status": "delayed",
                    "refund_amount": {"amount_minor": 499000, "currency": "VND"},
                },
            }
        )
    finally:
        llm.close()

    assert res["status"] == "draft_ready"
    assert res["draft"]["citations"] == [
        {
            "citation_id": "S2",
            "source_type": "order_context",
            "fields": ["placed_at", "shipping_cost", "shipment_status", "refund_amount"],
        }
    ]
    assert res["draft"]["segments"][0]["citation_ids"] == ["S2"]


def test_engine_draft_single_field_and_null_optional_field():
    """Single allowed field preserves field+fields compatibility while truly absent None fields are omitted."""
    req_model = SuggestionRequest(
        message="Is my parcel delayed?",
        order_context={"shipment_status": "delayed", "delivered_at": None},
        as_of="2026-10-20T00:00:00Z",
    )
    llm = _make_stub_gemini(answer="Your shipment status is delayed [S2].", citations=["S2"])
    try:
        eng = _make_engine(llm)
        res = eng.draft(req_model.model_dump())
    finally:
        llm.close()

    assert res["status"] == "draft_ready"
    assert res["draft"]["citations"] == [
        {
            "citation_id": "S2",
            "source_type": "order_context",
            "field": "shipment_status",
            "fields": ["shipment_status"],
        }
    ]


def test_engine_draft_fails_closed_when_order_context_missing_or_invalid_only():
    """Citing [S2] when order_context is empty or only invalid values still fails closed with grounding_failed."""
    for bad_ctx in ({}, {"order_total": {"amount_minor": 100, "currency": "VND", "extra": "bad"}}):
        llm = _make_stub_gemini(answer="Your order is delayed [S2].", citations=["S2"])
        try:
            eng = _make_engine(llm)
            eng.llm.generate = lambda *_a, **_kw: {
                "body": "Your order is delayed [S2].",
                "input_snapshot": {
                    "sources": [
                        {"source_id": "S1", "source_type": "policy", "document_id": "POL-SHIP-001", "version": "1.0", "excerpt": "Shipping"},
                        {"source_id": "S2", "source_type": "order_facts", "document_id": "ORDER-FACTS", "version": "facts", "excerpt": "Order"},
                    ]
                },
                "is_clarification": False,
                "latency_seconds": 0.05,
                "usage": {"promptTokenCount": 10, "candidatesTokenCount": 10, "totalTokenCount": 20},
            }
            res = eng.draft(
                {
                    "message": "Where is my order?",
                    "as_of": datetime.now(timezone.utc).isoformat(),
                    "order_context": bad_ctx,
                }
            )
            assert res["status"] == "llm_unavailable"
            assert "grounding_failed" in res["reason_codes"]
        finally:
            llm.close()


def test_jobs_hydrates_multi_field_order_citation_values_and_collector_verifies(monkeypatch):
    """Backend SuggestionWorker validates/hydrates multi-field order_context citations and fails closed on missing declared fields."""
    from apps.backend.tickets import jobs as jobs_mod

    monkeypatch.setattr(
        "apps.backend.tickets.privacy._get_spacy_nlp",
        lambda: (lambda _text: SimpleNamespace(ents=[])),
    )
    stored = []
    worker = SuggestionWorker(database=SimpleNamespace(), settings=SimpleNamespace(
        ai_service_base_url="http://ai.local",
        ai_service_analysis_timeout_ms=3000,
        ai_service_draft_timeout_ms=11000,
    ))
    monkeypatch.setattr(worker, "store", lambda *args, **kwargs: stored.append((args, kwargs)))

    order_ctx = {
        "order_status": "shipped",
        "shipping_cost": {"amount_minor": 0, "currency": "VND"},
        "shipment_status": "delayed",
        "refund_amount": {"amount_minor": 499000, "currency": "VND"},
    }
    analysis_payload = {
        "intent": {"label": "track_order", "probability": 0.95, "confidence_band": "high"},
        "alternatives": [],
        "documents": [],
        "warnings": [],
        "routing": {"recommendation": "draft", "reason_codes": []},
        "versions": {"release_id": "rel-1"},
    }

    def run_with_citations(citations):
        stored.clear()

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, json=None):
                if url.endswith("/v1/analyses"):
                    body = analysis_payload
                else:
                    body = {
                        "status": "draft_ready",
                        "reason_codes": [],
                        "analysis": analysis_payload,
                        "draft": {
                            "segments": [{"segment_id": "segment-0", "paragraph_index": 0, "text": "Shipping is 0 VND.", "citation_ids": ["S2"]}],
                            "citations": citations,
                        },
                    }
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)

        monkeypatch.setattr(jobs_mod.httpx, "Client", FakeClient)
        worker.process("sugg-1", "tok-1", {"message": "Shipping?", "as_of": "2026-10-20T00:00:00Z", "order_context": order_ctx})
        return stored[-1]

    args, _kwargs = run_with_citations([
        {"citation_id": "S2", "source_type": "order_context", "fields": ["shipping_cost", "shipment_status", "refund_amount"]}
    ])
    draft_result = args[3]
    hydrated_cit = draft_result["draft"]["citations"][0]
    assert hydrated_cit["values"] == {
        "shipping_cost": {"amount_minor": 0, "currency": "VND"},
        "shipment_status": "delayed",
        "refund_amount": {"amount_minor": 499000, "currency": "VND"},
    }

    # Verify AcceptanceEvidenceCollector helper accepts multi-field citation and rejects mismatch
    assert AcceptanceEvidenceCollector._verify_order_context_citation(hydrated_cit, order_ctx)["is_verified"] is True
    assert AcceptanceEvidenceCollector._verify_order_context_citation(hydrated_cit, {"shipping_cost": {"amount_minor": 0, "currency": "VND"}})["is_verified"] is False

    # Missing declared field in payload['order_context'] must fail closed in jobs.py
    bad_args, bad_kwargs = run_with_citations([
        {"citation_id": "S2", "source_type": "order_context", "fields": ["shipping_cost", "nonexistent_field"]}
    ])
    assert bad_args[3]["status"] == "unavailable"

    # Conflicting 'field' vs 'fields' must fail closed in jobs.py
    conflict_args, _ = run_with_citations([
        {
            "citation_id": "S2",
            "source_type": "order_context",
            "fields": ["order_status"],
            "field": "shipping_cost",
        }
    ])
    assert conflict_args[3]["status"] == "unavailable"


def test_flash_lite_inspect_case_citations_multi_field_legacy_and_fail_closed():
    """flash_lite_acceptance._inspect_case_citations shares verified multi-field/legacy/fail-closed behavior."""
    from pipeline.evaluation.flash_lite_acceptance import _inspect_case_citations

    class DummyCollector:
        def _build_source_snapshot(self, **kwargs):
            raise AssertionError("Document snapshot should not be called in order_context / invalid-source checks")

    executed_ctx = {
        "order_status": "shipped",
        "shipping_cost": {"amount_minor": 0, "currency": "VND"},
        "order_id": "ORD-SECRET-1",
    }
    collector = DummyCollector()

    # 1. Valid multi-field citation matches AcceptanceEvidenceCollector
    multi_cit = {
        "citation_id": "S2",
        "source_type": "order_context",
        "fields": ["order_status", "shipping_cost"],
        "values": {
            "order_status": "shipped",
            "shipping_cost": {"amount_minor": 0, "currency": "VND"},
        },
    }
    parsed, _ = _inspect_case_citations([multi_cit], [], executed_ctx, collector)
    assert len(parsed) == 1
    assert parsed[0] == AcceptanceEvidenceCollector._verify_order_context_citation(multi_cit, executed_ctx)
    assert parsed[0]["is_verified"] is True
    assert parsed[0]["field_present_in_executed_context"] is True
    assert parsed[0]["value_matches_executed_context"] is True

    # 2. Valid legacy single-field citation remains compatible
    legacy_cit = {"citation_id": "S2", "source_type": "order_context", "field": "order_status", "value": "shipped"}
    parsed_legacy, _ = _inspect_case_citations([legacy_cit], [], executed_ctx, collector)
    assert parsed_legacy[0]["is_verified"] is True

    # 3. Missing/unknown/disallowed/mismatched/arbitrary IDs/bool-int confusion fail closed
    invalid_cases = [
        # Missing field in executed context
        {"source_type": "order_context", "fields": ["order_status", "refund_status"], "values": {"order_status": "shipped", "refund_status": "paid"}},
        # Legacy missing field
        {"source_type": "order_context", "field": "refund_status", "value": "paid"},
        # Arbitrary disallowed ID even if present in ctx
        {"source_type": "order_context", "fields": ["order_id"], "values": {"order_id": "ORD-SECRET-1"}},
        {"source_type": "order_context", "field": "order_id", "value": "ORD-SECRET-1"},
        {"source_type": "order_context", "field": "tracking_code", "value": "TRK-1"},
        # Bool/int confusion: False != 0
        {"source_type": "order_context", "fields": ["shipping_cost"], "values": {"shipping_cost": {"amount_minor": False, "currency": "VND"}}},
        # Mismatched value & extra/missing values keys
        {"source_type": "order_context", "fields": ["order_status"], "values": {"order_status": "delivered"}},
        {"source_type": "order_context", "fields": ["order_status"], "values": {"order_status": "shipped", "extra": 1}},
        {"source_type": "order_context", "fields": ["order_status"]},
        # Empty/duplicate fields list or conflicting single field
        {"source_type": "order_context", "fields": [], "values": {}},
        {"source_type": "order_context", "fields": ["order_status", "order_status"], "values": {"order_status": "shipped"}},
        {"source_type": "order_context", "fields": ["order_status"], "values": {"order_status": "shipped"}, "field": "shipping_cost", "value": {"amount_minor": 0, "currency": "VND"}},
        # Arbitrary source type even with known document_id
        {"source_type": "arbitrary_source", "document_id": "POL-RET-001", "version": "2.0"},
    ]
    for bad_cit in invalid_cases:
        out, _ = _inspect_case_citations([bad_cit], [], executed_ctx, collector)
        assert out[0]["is_verified"] is False, f"Expected fail-closed verification for {bad_cit}"


def test_engine_draft_direct_call_mixed_s1_s2_legacy_only_fails_closed():
    """Direct Engine.draft call with legacy-only order_context must fail closed instead of dropping [S2]."""
    llm = _make_stub_gemini(
        answer="Orders ship within 1-2 business days and carrier handles tracking [S1][S2].",
        citations=["S1", "S2"],
    )
    try:
        eng = _make_engine(llm)
        res = eng.draft(
            {
                "message": "My parcel is delayed, how do returns and carrier tracking work?",
                "as_of": datetime.now(timezone.utc).isoformat(),
                "order_context": {"carrier": "VNPost"},
            }
        )
    finally:
        llm.close()
    assert res["status"] == "llm_unavailable"
    assert "grounding_failed" in res["reason_codes"]
