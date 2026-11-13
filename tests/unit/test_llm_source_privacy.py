"""Focused regression tests for LLM source-egress privacy vs internal staff grounding contract."""

from __future__ import annotations

import hashlib
import json

import httpx

from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext
from apps.core_backend.llm.gemini import (
    GeminiDraftClient,
    build_grounded_sources,
    prepare_llm_input,
    redact_contacts,
)
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore


def _verified_ship_policy() -> dict:
    content = (
        "In the event a Tiki order exceeds its estimated delivery date without arrival, "
        "or if a courier marks an order as 'Successfully Delivered' when the customer has not received the parcel, "
        "the customer must contact Tiki Customer Support within 24-48 hours via hotline 1900 6035. "
        "Tiki's dispatch team will verify courier GPS logs, coordinate with the delivery hub, and resolve the complaint. "
        "If an order is lost, Tiki will dispatch a replacement or issue a 100% refund."
    )
    return {
        "source_type": "policy",
        "document_id": "POL-SHIP-004",
        "version": "1.0",
        "title": "Handling Delayed, Lost, or Discrepant Delivery Statuses",
        "excerpt": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "status": "approved",
    }


def test_mock_transport_serialized_payload_excludes_raw_order_and_tracking_canaries():
    captured_raw_bodies: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured_raw_bodies.append(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-3.5-flash-lite",
                "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 12},
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "answerable": True,
                                            "answer": "Your order is Shipping [S2] and returns apply for 30 days [S1].",
                                            "citations": ["S1", "S2"],
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ],
            },
        )

    canary_order = {
        "order_id": "ORD-991042",
        "tracking_code": "GIAO89254563",
        "customer_id": "cust-canary-77",
        "customer_name": "Bui Thi Canary",
        "phone": "0938242854",
        "email": "canary@example.com",
        "order_status": "Shipping",
        "payment_status": "Captured",
        "delivery_date": "2026-11-05",
        "estimated_delivery": "Within 1-2 business days via GHN Express",
        "carrier": "GHN Express",
        "can_cancel": False,
    }
    ret_policy = {
        "document_id": "POL-RET-001",
        "version": "2.0",
        "title": "Tiki Return Policy",
        "excerpt": "Tiki accepts returns within 30 days for orders up to 500000 VND.",
    }
    customer_q = (
        "Where is ORD-991042 / GIAO89254563 from Tiki via GHN Express "
        "shipped on 2026-11-05 worth 500000 VND? Call 0938242854 or Bui Thi Canary."
    )

    client = GeminiDraftClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        res = client.generate(customer_q, "track_order", [ret_policy], business_context=canary_order)
    finally:
        client.close()

    assert len(captured_raw_bodies) == 1
    wire_payload = captured_raw_bodies[0]

    for secret in ("ORD-991042", "GIAO89254563", "cust-canary-77", "Bui Thi Canary", "0938242854", "canary@example.com"):
        assert secret not in wire_payload

    for preserved in ("Tiki", "GHN Express", "2026-11-05", "500000 VND", "30 days", "Shipping"):
        assert preserved in wire_payload

    prompt_obj = json.loads(json.loads(wire_payload)["contents"][0]["parts"][0]["text"])
    assert prompt_obj["sources"][1]["source_type"] == "order_facts"
    assert prompt_obj["sources"][1]["document_id"] == "ORDER-FACTS"

    s2 = res["input_snapshot"]["sources"][1]
    assert s2["source_type"] == "order_facts"
    assert s2["document_id"] == "ORD-991042"
    assert res["citations"][1] == {
        "source_id": "S2",
        "source_type": "order_facts",
        "document_id": "ORD-991042",
        "version": "facts",
    }


def test_prepare_llm_input_preserves_verified_policy_public_contact_provenance():
    snapshot = prepare_llm_input(
        question="Delayed order ORD-1001 tracking TIKI71662963 expected 2026-11-05",
        intent="delivery_issue",
        evidence=[_verified_ship_policy()],
        business_context={
            "order_id": "ORD-1001",
            "tracking_code": "TIKI71662963",
            "order_status": "Shipping",
            "delivery_date": "2026-11-05",
        },
    )
    prompt = snapshot["prompt"]
    assert "ORD-1001" not in prompt
    assert "TIKI71662963" not in prompt
    assert "1900 6035" in prompt
    assert "2026-11-05" in prompt
    assert "POL-SHIP-004" in prompt


def test_pipeline_runner_preserves_snapshot_citations_with_pseudonymized_prompt_sources(tmp_path):
    wire_bodies: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        wire_bodies.append(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "answerable": True,
                                            "answer": "Your order is Shipping [S2].",
                                            "citations": ["S2"],
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
        )

    class _Intent:
        def classify_intent(self, text, request_id=None):
            return IntentPrediction(intent="track_order", confidence=0.99, margin=0.9, model_version="v1.0.0")

    class _Commerce:
        def lookup_order(self, order_id, ticket_customer_id=None, verified_scope=""):
            return {
                "authorized": True,
                "order": {
                    "order_id": "ORD-7788",
                    "tracking_code": "VNPOST991122",
                    "order_status": "Shipping",
                    "carrier": "GHN Express",
                },
            }

    class _Retrieval:
        def retrieve(self, text, intent, role="agent", current_time=None):
            return {"status": "success", "evidence": [{"document_id": "POL-ORD-001", "version": "1.0", "excerpt": "Track in My Orders."}]}

    store = PersistentStore(str(tmp_path / "runs.sqlite3"))
    llm = GeminiDraftClient(api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        runner = PipelineRunner(
            intent_client=_Intent(),
            commerce_adapter=_Commerce(),
            retrieval_adapter=_Retrieval(),
            store=store,
            llm_client=llm,
        )
        out = runner.run(
            "Where is ORD-7788 VNPOST991122?",
            RoutingContext(ticket_customer_id="cust-1", is_personal_lookup=True, extracted_slots={"order_id": "ORD-7788"}),
            run_id="privacy-pipe-1",
        )
    finally:
        llm.close()

    assert out["action"] == "retrieve_draft"
    assert len(wire_bodies) == 1
    assert "ORD-7788" not in wire_bodies[0]
    assert "VNPOST991122" not in wire_bodies[0]
    assert "GHN Express" in wire_bodies[0]
    prompt_obj = json.loads(json.loads(wire_bodies[0])["contents"][0]["parts"][0]["text"])
    assert prompt_obj["sources"][1]["document_id"] == "ORDER-FACTS"
    assert out["llm_input_snapshot"]["sources"][1]["document_id"] == "ORD-7788"


def test_build_grounded_sources_default_preserves_internal_staff_contract():
    sources = build_grounded_sources(
        [{"document_id": "POL-RET-001", "version": "2.0", "excerpt": "Return within 30 days."}],
        {"order_id": "ORD-991042", "tracking_code": "GIAO89254563", "order_status": "Shipping"},
    )
    assert sources[1]["document_id"] == "ORD-991042"
    assert "GIAO89254563" in sources[1]["excerpt"]


def test_redact_contacts_preserves_exact_datetime_and_dotted_currency_with_negative_phone_controls():
    # Positive controls: exact dates, datetimes, dotted currency amounts
    assert redact_contacts("It was delivered on 2026-11-05.") == "It was delivered on 2026-11-05."
    assert redact_contacts("It was delivered on 2026-11-05 14:30.") == "It was delivered on 2026-11-05 14:30."
    assert redact_contacts("Shipped at 2026-11-05T14:30:00.") == "Shipped at 2026-11-05T14:30:00."
    assert redact_contacts("Orders above 1.000.000 VND ship free.") == "Orders above 1.000.000 VND ship free."
    assert redact_contacts("Refund cap 2.500.000 VNĐ and 1.250.000 đ.") == "Refund cap 2.500.000 VNĐ and 1.250.000 đ."

    # Negative phone controls & adversarial inputs must still mask phone numbers
    assert redact_contacts("Call me at 0938 242 854 please") == "Call me at [PHONE_OR_NUMBER] please"
    assert redact_contacts("My number is 0938.242.854") == "My number is [PHONE_OR_NUMBER]"
    assert redact_contacts("Phone +84 938 242 854") == "Phone [PHONE_OR_NUMBER]"
    assert redact_contacts("Adversarial 0938.242.854 VND") == "Adversarial [PHONE_OR_NUMBER] VND"
    assert redact_contacts("Bare dotted 123.456.789") == "Bare dotted [PHONE_OR_NUMBER]"
    assert redact_contacts("Invalid date 2026-99-99 99:99") == "Invalid date [PHONE_OR_NUMBER]:99"
    assert (
        redact_contacts("Delivered 2026-11-05 14:30 for 1.000.000 VND, call 0938 242 854")
        == "Delivered 2026-11-05 14:30 for 1.000.000 VND, call [PHONE_OR_NUMBER]"
    )

    # Verified policy hotline still requires allowed_numbers provenance
    assert redact_contacts("Hotline 1900 6035") == "Hotline [PHONE_OR_NUMBER]"
    assert redact_contacts("Hotline 1900 6035", allowed_numbers=("1900 6035",)) == "Hotline 1900 6035"


def test_only_identifier_order_context_keeps_prompt_and_snapshot_source_ids_coherent():
    evidence = [
        {
            "source_type": "policy",
            "document_id": "POL-SHIP-001",
            "version": "1.0",
            "title": "Shipping Policy",
            "excerpt": "Tracking updates appear once the courier scans the parcel.",
        }
    ]
    only_id_context = {"order_id": "ORD-445566", "tracking_code": "GIAO44556677"}

    snapshot = prepare_llm_input(
        "Where is ORD-445566 GIAO44556677?",
        "track_order",
        evidence,
        business_context=only_id_context,
    )
    prompt_obj = json.loads(snapshot["prompt"])

    assert [s["source_id"] for s in prompt_obj["sources"]] == [s["source_id"] for s in snapshot["sources"]] == ["S1", "S2"]
    assert prompt_obj["sources"][1]["document_id"] == "ORDER-FACTS"
    assert snapshot["sources"][1]["document_id"] == "ORD-445566"
    assert "ORD-445566" not in snapshot["prompt"]
    assert "GIAO44556677" not in snapshot["prompt"]

    # End-to-end MockTransport verification with only-ID context citing [S2]
    captured: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "answerable": True,
                                            "answer": "Tracking details are on file [S2] per shipping policy [S1].",
                                            "citations": ["S1", "S2"],
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
        )

    client = GeminiDraftClient(api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        res = client.generate("Where is ORD-445566?", "track_order", evidence, business_context=only_id_context)
    finally:
        client.close()

    assert "ORD-445566" not in captured[0]
    assert "GIAO44556677" not in captured[0]
    assert [c["source_id"] for c in res["citations"]] == ["S1", "S2"]
