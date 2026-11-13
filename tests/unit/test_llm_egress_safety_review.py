"""Independent egress and privacy contract review tests for LLM prompt serialization.

Verifies serialized HTTP request payloads sent via MockTransport rather than
mirroring internal redactor regex implementation details.
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext
from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore


_POL_SHIP_004_CONTENT = (
    "In the event a Tiki order exceeds its estimated delivery date without arrival, "
    "or if a courier marks an order as 'Successfully Delivered' when the customer has not received the parcel, "
    "the customer must contact Tiki Customer Support within 24-48 hours via hotline 1900 6035. "
    "Tiki's dispatch team will verify courier GPS logs, coordinate with the delivery hub, and resolve the complaint. "
    "If an order is lost, Tiki will dispatch a replacement or issue a 100% refund."
)
_POL_SHIP_004_HASH = hashlib.sha256(_POL_SHIP_004_CONTENT.encode("utf-8")).hexdigest()


def _make_client(captured_bodies: list[str], answer: str = "Your order is Delivered [S1][S2].", citations=None):
    cit = ["S1", "S2"] if citations is None else citations

    def handler(req: httpx.Request) -> httpx.Response:
        captured_bodies.append(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-2.5-flash",
                "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 12, "totalTokenCount": 62},
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [{"text": json.dumps({"answerable": True, "answer": answer, "citations": cit})}]
                        },
                    }
                ],
            },
        )

    return GeminiDraftClient(
        api_key="review-fake-secret-key",
        model="gemini-2.5-flash",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_serialized_egress_excludes_raw_identifiers_across_arbitrary_allowed_fact_fields():
    captured: list[str] = []
    client = _make_client(captured)
    business_context = {
        "order_id": "ORD-884422",
        "tracking_code": "GIAO77665544",
        "customer_id": "cust-771122",
        "transaction_id": "TIKI-TXN-332211",
        "customer_name": "Nguyen Minh Khang",
        "phone": "0912345678",
        "email": "khang.nguyen@example.com",
        "order_status": "Delivered for Nguyen Minh Khang",
        "payment_status": "Paid via TIKI-TXN-332211",
        "refund_status": "Requested by cust-771122",
        "delivery_date": "2026-11-05",
        "estimated_delivery": "2026-11-06 for ORD-884422",
        "expected_refund_time": "3-5 days after GIAO77665544 return",
        "carrier": "GHN Express (GIAO77665544)",
        "can_cancel": False,
        "eligible_for_return": True,
    }
    evidence = [
        {
            "source_type": "policy",
            "document_id": "POL-RET-001",
            "version": "1.0",
            "title": "Return Policy",
            "excerpt": "Returns are accepted within 30 days.",
        }
    ]

    try:
        res = client.generate(
            "Check ORD-884422 / GIAO77665544 for Nguyen Minh Khang (khang.nguyen@example.com, 0912345678)",
            "track_order",
            evidence,
            business_context=business_context,
        )
    finally:
        client.close()

    assert len(captured) == 1
    wire = captured[0]
    for secret in (
        "review-fake-secret-key",
        "ORD-884422",
        "GIAO77665544",
        "cust-771122",
        "TIKI-TXN-332211",
        "Nguyen Minh Khang",
        "0912345678",
        "khang.nguyen@example.com",
    ):
        assert secret not in wire

    prompt_obj = json.loads(json.loads(wire)["contents"][0]["parts"][0]["text"])
    assert prompt_obj["sources"][1]["document_id"] == "ORDER-FACTS"
    assert "GHN Express" in wire
    assert "2026-11-05" in wire
    assert res["input_snapshot"]["sources"][1]["document_id"] == "ORD-884422"


def test_serialized_egress_masks_known_identifiers_and_names_in_policy_text_and_title():
    captured: list[str] = []
    client = _make_client(captured, answer="Please see the return policy [S1].", citations=["S1"])
    business_context = {
        "order_id": "ORD-991042",
        "tracking_code": "GIAO89254563",
        "customer_id": "cust-8821",
        "transaction_id": "TXN-554433",
        "customer_name": "Bui Thi An",
        "order_status": "Shipping",
    }
    evidence = [
        {
            "source_type": "policy",
            "document_id": "POL-RET-001",
            "version": "1.0",
            "title": "Return Terms for Bui Thi An",
            "excerpt": "Applies to Bui Thi An shipment GIAO89254563 and payment TXN-554433 on ORD-991042.",
        }
    ]

    try:
        client.generate("What applies to my order?", "return_policy", evidence, business_context=business_context)
    finally:
        client.close()

    wire = captured[0]
    for known in ("ORD-991042", "GIAO89254563", "cust-8821", "TXN-554433", "Bui Thi An"):
        assert known not in wire


def test_short_identifier_controls_preserve_normal_words_without_leaking_order_fields():
    captured: list[str] = []
    client = _make_client(captured)
    short_context = {
        "order_id": "10",
        "tracking_code": "A1B",
        "customer_name": "An",
        "order_status": "Packed",
    }
    evidence = [
        {
            "source_type": "policy",
            "document_id": "POL-RET-001",
            "version": "1.0",
            "excerpt": "Returns accepted within 10 days for an eligible item.",
        }
    ]

    try:
        client.generate(
            "Can I return an order within 10 days?",
            "return_policy",
            evidence,
            business_context=short_context,
        )
    finally:
        client.close()

    wire = captured[0]
    prompt_obj = json.loads(json.loads(wire)["contents"][0]["parts"][0]["text"])
    assert "within 10 days" in prompt_obj["question"]
    assert "an order" in prompt_obj["question"]
    assert "within 10 days" in prompt_obj["sources"][0]["excerpt"]
    assert "an eligible item" in prompt_obj["sources"][0]["excerpt"]
    assert "A1B" not in wire
    assert prompt_obj["sources"][1]["document_id"] == "ORDER-FACTS"
    assert "order_id" not in prompt_obj["order_facts"]
    assert "tracking_code" not in prompt_obj["order_facts"]


def test_snapshot_sources_citations_and_prompt_sha256_contract_coherence(tmp_path):
    captured: list[str] = []
    client = _make_client(captured, answer="Returns take 30 days [S1]. Order is Shipping [S2].", citations=["S1", "S2"])

    class _Intent:
        def classify_intent(self, text, request_id=None):
            return IntentPrediction(intent="track_order", confidence=0.98, margin=0.90, model_version="v1.0.0")

    class _Commerce:
        def lookup_order(self, order_id, ticket_customer_id=None, verified_scope=""):
            return {
                "authorized": True,
                "order": {
                    "order_id": "ORD-991042",
                    "tracking_code": "GIAO89254563",
                    "customer_name": "Tran Thi Mai",
                    "order_status": "Shipping",
                    "delivery_date": "2026-11-05",
                },
            }

    class _Retrieval:
        def retrieve(self, text, intent, role="agent", current_time=None):
            return {
                "status": "success",
                "evidence": [
                    {
                        "source_type": "policy",
                        "document_id": "POL-RET-001",
                        "version": "2.0",
                        "title": "Return Policy",
                        "excerpt": "Returns take 30 days in original packaging.",
                    }
                ],
            }

    runner = PipelineRunner(
        intent_client=_Intent(),
        commerce_adapter=_Commerce(),
        retrieval_adapter=_Retrieval(),
        store=PersistentStore(str(tmp_path / "runs.sqlite3")),
        llm_client=client,
    )
    try:
        out = runner.run(
            "Where is ORD-991042 (GIAO89254563) for Tran Thi Mai?",
            RoutingContext(ticket_customer_id="cust-1", is_personal_lookup=True, extracted_slots={"order_id": "ORD-991042"}),
            run_id="egress-coherence-1",
        )
    finally:
        client.close()

    assert out["action"] == "retrieve_draft"
    assert out["must_human_approve"] is True
    assert out["can_execute_transaction"] is False
    assert len(captured) == 1
    wire = captured[0]
    for raw_secret in ("ORD-991042", "GIAO89254563", "Tran Thi Mai"):
        assert raw_secret not in wire

    snapshot = out["llm_input_snapshot"]
    assert snapshot["sha256"] == hashlib.sha256(snapshot["prompt"].encode("utf-8")).hexdigest()

    prompt_obj = json.loads(snapshot["prompt"])
    for src in prompt_obj["sources"] + snapshot["sources"]:
        assert src["source_id"] == src["id"]
        assert src["sha256"] == hashlib.sha256(src["excerpt"].encode("utf-8")).hexdigest()

    assert prompt_obj["sources"][1]["document_id"] == "ORDER-FACTS"
    assert snapshot["sources"][1]["document_id"] == "ORD-991042"
    assert out["llm"]["citations"] == [
        {"source_id": "S1", "source_type": "policy", "document_id": "POL-RET-001", "version": "2.0"},
        {"source_id": "S2", "source_type": "order_facts", "document_id": "ORD-991042", "version": "facts"},
    ]


@pytest.mark.parametrize(
    ("content_hash", "expect_hotline_preserved", "answer"),
    [
        (
            _POL_SHIP_004_HASH,
            True,
            "Call hotline 1900 6035 within 24-48 hours [S1] regarding order delivered on 2026-11-05 [S2].",
        ),
        (
            "0" * 64,
            False,
            "Please check your delayed delivery details for 2026-11-05 [S2] and contact support [S1].",
        ),
    ],
)
def test_positive_controls_preserve_iso_date_and_verified_hotline_only_with_valid_provenance(
    content_hash, expect_hotline_preserved, answer
):
    captured: list[str] = []
    client = _make_client(captured, answer=answer, citations=["S1", "S2"])
    evidence = [
        {
            "source_type": "policy",
            "document_id": "POL-SHIP-004",
            "version": "1.0",
            "title": "Handling Delayed, Lost, or Discrepant Delivery Statuses",
            "status": "approved",
            "content_hash": content_hash,
            "excerpt": _POL_SHIP_004_CONTENT,
        }
    ]

    try:
        res = client.generate(
            "Delayed delivery since 2026-11-05",
            "delivery_issue",
            evidence,
            business_context={"order_id": "ORD-5555", "delivery_date": "2026-11-05", "order_status": "Delayed"},
        )
    finally:
        client.close()

    assert res["body"] == answer
    wire = captured[0]
    assert "ORD-5555" not in wire
    assert "2026-11-05" in wire
    assert ("1900 6035" in wire) is expect_hotline_preserved


def test_negative_controls_reject_unsupported_date_citation_and_tampered_hotline():
    # 1. Valid provenance, but draft cites [S1] alone for a date only present in [S2] -> fail closed
    captured_date: list[str] = []
    client_date = _make_client(
        captured_date,
        answer="Call hotline 1900 6035 regarding 2026-11-05 [S1].",
        citations=["S1"],
    )
    ev_valid = [
        {
            "source_type": "policy",
            "document_id": "POL-SHIP-004",
            "version": "1.0",
            "title": "Handling Delayed, Lost, or Discrepant Delivery Statuses",
            "status": "approved",
            "content_hash": _POL_SHIP_004_HASH,
            "excerpt": _POL_SHIP_004_CONTENT,
        }
    ]
    ctx = {"order_id": "ORD-5555", "delivery_date": "2026-11-05", "order_status": "Delayed"}

    try:
        with pytest.raises(LLMError) as exc_date:
            client_date.generate("Delayed delivery since 2026-11-05", "delivery_issue", ev_valid, business_context=ctx)
        assert exc_date.value.code == "llm_invalid_citations"
    finally:
        client_date.close()

    assert "ORD-5555" not in captured_date[0]
    assert "1900 6035" in captured_date[0]
    assert "2026-11-05" in captured_date[0]

    # 2. Tampered content_hash masks hotline in wire AND fail-closes if draft outputs 1900 6035
    captured_tampered: list[str] = []
    client_tampered = _make_client(
        captured_tampered,
        answer="Call hotline 1900 6035 within 24-48 hours [S1].",
        citations=["S1"],
    )
    ev_tampered = [{**ev_valid[0], "content_hash": "0" * 64}]
    try:
        with pytest.raises(LLMError) as exc_tampered:
            client_tampered.generate(
                "Delayed delivery since 2026-11-05", "delivery_issue", ev_tampered, business_context=ctx
            )
        assert exc_tampered.value.code == "llm_invalid_citations"
    finally:
        client_tampered.close()

    assert "ORD-5555" not in captured_tampered[0]
    assert "1900 6035" not in captured_tampered[0]
    assert "2026-11-05" in captured_tampered[0]
