"""Independent grounding, numeric, sentence-split, commitment, and queue propagation review tests.

Tests observable behavior through GeminiDraftClient (httpx.MockTransport),
PipelineRunner + PersistentStore, and shared safety validators without mirroring
internal regex patterns.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing

import httpx
import pytest

from apps.core_backend import safety as safety_mod
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

_EV_SHIP = [
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

_EV_RET = [
    {
        "source_type": "policy",
        "document_id": "POL-RET-001",
        "version": "1.0",
        "title": "Return Policy",
        "excerpt": "Returns are accepted within 30 days in original packaging. Delivered on 2026-11-05.",
    }
]


def _mock_gemini_client(answer: str, citations=("S1",), *, answerable: bool = True) -> GeminiDraftClient:
    def handler(req: httpx.Request) -> httpx.Response:
        payload = {"answerable": answerable, "answer": answer, "citations": list(citations)}
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-2.5-flash",
                "usageMetadata": {"promptTokenCount": 40, "candidatesTokenCount": 12, "totalTokenCount": 52},
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}],
            },
        )

    return GeminiDraftClient(
        api_key="review-fake-key",
        model="gemini-2.5-flash",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _run_pipeline(tmp_path, run_id: str, evidence, *, llm_client, business_context=None):
    class _Intent:
        def classify_intent(self, text, request_id=None):
            return IntentPrediction(intent="return_policy", confidence=0.99, margin=0.95, model_version="v1.0.0")

    class _Retrieval:
        def retrieve(self, text, intent, role="agent", current_time=None):
            return {"status": "success", "evidence": evidence}

    class _Commerce:
        def lookup_order(self, order_id, ticket_customer_id=None, verified_scope=""):
            return {"authorized": True, "order": business_context}

    store = PersistentStore(str(tmp_path / f"{run_id}.sqlite3"))
    runner = PipelineRunner(
        intent_client=_Intent(),
        commerce_adapter=_Commerce(),
        retrieval_adapter=_Retrieval(),
        store=store,
        llm_client=llm_client,
    )
    slots = {"order_id": business_context["order_id"]} if business_context and "order_id" in business_context else {}
    ctx = RoutingContext(ticket_customer_id="cust-1", verified_scope="ticket:read", extracted_slots=slots)
    return runner.run("Check policy and order details.", ctx, run_id=run_id), store


@pytest.mark.parametrize(
    ("evidence", "tampered_draft"),
    [
        (_EV_SHIP, "Refunds arrive within 5 days [S1]."),
        (_EV_SHIP, "Returns are accepted within 35 days [S1]."),
        (_EV_SHIP, "We offer a 90% refund [S1]."),
        (_EV_RET, "Shipping takes 11 weeks [S1]."),
    ],
)
def test_numeric_claims_must_not_pass_as_substring_of_hotline_or_date_digit_runs(
    tmp_path, evidence, tampered_draft
):
    client = _mock_gemini_client(tampered_draft, citations=["S1"])
    try:
        with pytest.raises(LLMError) as exc_info:
            client.generate("Check policy", "return_policy", evidence)
        assert exc_info.value.code == "llm_invalid_citations"
    finally:
        client.close()

    pipe_client = _mock_gemini_client(tampered_draft, citations=["S1"])
    try:
        out, _ = _run_pipeline(tmp_path, "num-bypass-check", evidence, llm_client=pipe_client)
    finally:
        pipe_client.close()
    assert out["action"] == "manual_fallback"
    assert out["draft_body"] is None
    assert out["must_human_approve"] is True


def test_lowercase_second_sentence_uncited_claim_is_rejected(tmp_path):
    draft = "Returns are accepted within 30 days [S1]. refunds are always approved automatically."
    client = _mock_gemini_client(draft, citations=["S1"])
    try:
        with pytest.raises(LLMError) as exc_info:
            client.generate("Return window?", "return_policy", _EV_RET)
        assert exc_info.value.code == "llm_invalid_citations"
    finally:
        client.close()

    pipe_client = _mock_gemini_client(draft, citations=["S1"])
    try:
        out, _ = _run_pipeline(tmp_path, "lowercase-uncited", _EV_RET, llm_client=pipe_client)
    finally:
        pipe_client.close()
    assert out["action"] == "manual_fallback"
    assert out["draft_body"] is None


def test_customer_attribution_does_not_swallow_real_assistant_commitment(tmp_path):
    draft = "You asked about shipping and we have refunded your order [S1]."
    client = _mock_gemini_client(draft, citations=["S1"])
    try:
        with pytest.raises(LLMError) as exc_info:
            client.generate("Shipping status?", "return_policy", _EV_RET)
        assert exc_info.value.code == "llm_invalid_citations"
    finally:
        client.close()

    pipe_client = _mock_gemini_client(draft, citations=["S1"])
    try:
        out, _ = _run_pipeline(tmp_path, "attr-commit", _EV_RET, llm_client=pipe_client)
    finally:
        pipe_client.close()
    assert out["action"] == "manual_fallback"
    assert out["draft_body"] is None


def test_abbreviations_and_conditional_policy_sentences_are_not_falsely_rejected(tmp_path):
    abbrev_draft = "Returns apply, e.g. Approx. 30 days in original packaging [S1]."
    cond_draft = "If an order is lost, we will refund your order [S1]."

    for run_id, ev, draft in (
        ("abbrev-ok", _EV_RET, abbrev_draft),
        ("cond-ok", _EV_SHIP, cond_draft),
    ):
        client = _mock_gemini_client(draft, citations=["S1"])
        try:
            res = client.generate("Policy question?", "return_policy", ev)
        finally:
            client.close()
        assert res["body"] == draft

        pipe_client = _mock_gemini_client(draft, citations=["S1"])
        try:
            out, _ = _run_pipeline(tmp_path, run_id, ev, llm_client=pipe_client)
        finally:
            pipe_client.close()
        assert out["action"] == "retrieve_draft"
        assert out["draft_body"] == draft


def test_recorded_cancelled_or_refunded_order_status_is_preserved_not_rejected_as_execution(tmp_path):
    order_ctx = {"order_id": "ORD-1009", "order_status": "Cancelled", "refund_status": "Refunded"}
    draft = "Your order was cancelled and your refund is already refunded [S2]."
    client = _mock_gemini_client(draft, citations=["S2"])
    try:
        res = client.generate("What is my order status?", "track_order", _EV_RET, business_context=order_ctx)
    finally:
        client.close()
    assert res["body"] == draft

    pipe_client = _mock_gemini_client(draft, citations=["S2"])
    try:
        out, _ = _run_pipeline(tmp_path, "recorded-status", _EV_RET, llm_client=pipe_client, business_context=order_ctx)
    finally:
        pipe_client.close()
    assert out["action"] == "retrieve_draft"
    assert out["draft_body"] == draft


def test_positive_controls_greetings_hotline_dates_quoted_claims_and_currency():
    # Greeting, hotline 1900 6035, and policy timeframe through real MockTransport client
    client = _mock_gemini_client(
        "Hello! Please contact support within 24-48 hours via hotline 1900 6035 [S1]. Thank you!",
        citations=["S1"],
    )
    try:
        res_ship = client.generate("Delayed package?", "delivery_issue", _EV_SHIP)
    finally:
        client.close()
    assert "1900 6035" in res_ship["body"]

    # Date + quoted customer execution claim + period-before-citation
    client_ret = _mock_gemini_client(
        'You wrote "my order has been cancelled", returns take 30 days since 2026-11-05.[S1] Thank you!',
        citations=["S1"],
    )
    try:
        res_ret = client_ret.generate("Order check", "return_policy", _EV_RET)
    finally:
        client_ret.close()
    assert "2026-11-05" in res_ret["body"]

    # Currency canonical equivalence (dotted VND vs compact integer) in shared safety validator
    find_violation = getattr(safety_mod, "find_draft_grounding_violation", None)
    if find_violation is not None:
        vnd_sources = [
            {
                "source_id": "S1",
                "source_type": "policy",
                "document_id": "POL-RET-002",
                "version": "1.0",
                "excerpt": "Orders above 1.000.000 VND ship free within 5 to 7 business days.",
            }
        ]
        assert (
            find_violation(
                "Shipping cost?",
                "Orders above 1000000 VND ship free within 5 to 7 business days [S1].",
                vnd_sources,
            )
            is None
        )


def test_pipeline_runner_propagates_grounding_rejection_and_abstention_to_runs_and_queue(tmp_path):
    # 1. Invalid tampered number raised by GeminiDraftClient -> manual_fallback with no draft saved
    tampered_client = _mock_gemini_client("Returns are accepted within 45 days [S1].", citations=["S1"])
    try:
        out_fb, store_fb = _run_pipeline(tmp_path, "pipe-num-reject", _EV_RET, llm_client=tampered_client)
    finally:
        tampered_client.close()
    assert out_fb["action"] == "manual_fallback"
    assert out_fb["draft_body"] is None
    assert out_fb["must_human_approve"] is True
    assert "llm_invalid_citations" in out_fb["reason_codes"]
    with closing(sqlite3.connect(str(store_fb.db_path))) as con:
        saved = json.loads(con.execute("SELECT payload_json FROM runs WHERE run_id=?", ("pipe-num-reject",)).fetchone()[0])
    assert saved["action"] == "manual_fallback" and saved["draft_body"] is None

    # 2. Explicit abstention (answerable=false) -> escalate + escalation_queue row
    abstain_client = _mock_gemini_client("", citations=[], answerable=False)
    try:
        out_esc, store_esc = _run_pipeline(tmp_path, "pipe-abstain-esc", _EV_RET, llm_client=abstain_client)
    finally:
        abstain_client.close()
    assert out_esc["action"] == "escalate"
    assert out_esc["draft_body"] is None
    assert "llm_insufficient_evidence" in out_esc["reason_codes"]
    with closing(sqlite3.connect(str(store_esc.db_path))) as con:
        esc_count = con.execute("SELECT COUNT(*) FROM escalation_queue WHERE run_id=?", ("pipe-abstain-esc",)).fetchone()[0]
    assert esc_count == 1

    # 3. Direct client bypass returning uncited claim -> downstream validate_generated_draft rejects cleanly
    class _BypassLLM:
        configured = True

        def generate(self, question, intent, evidence, business_context=None):
            return {
                "body": "Returns are accepted within 30 days [S1]. Refunds arrive in 2 hours.",
                "citations": ["S1"],
            }

    out_post, _ = _run_pipeline(tmp_path, "pipe-post-reject", _EV_RET, llm_client=_BypassLLM())
    assert out_post["action"] == "manual_fallback"
    assert out_post["draft_body"] is None
    assert "grounding_failed" in out_post["reason_codes"]
