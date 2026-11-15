"""Worker C Independent order_context 10-Field Contract Parity & Adversarial Verification.

Zero live LLM/paid calls, zero service restarts, zero production edits.
Exercises:
- Backend `order_context(order)` across all 10 canonical fields + precedence + non-dict/None/malformed inputs
- Strict privacy gate (`validate_egress_payload` with real spaCy NER) + `SuggestionRequest` schema
- `Engine.draft` prompt/grounding/citations with fake HTTP `MockTransport` LLM (discovering real order_facts S# id)
- Authoritative fact non-fabrication (prose ETA/refund time must not invent dates; fabricated date/amount/commitment rejected)
- `SuggestionWorker` citation hydration (`fields` + single-`field`) and full disposable-PG ticket->worker->console flow
- Preserved core invariant SHA-256 digests and 2/2 STOP training cap
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("PSYCOPG_IMPL", "python")
pg_bin = Path("F:/PostgreSQL/bin")
if pg_bin.exists() and str(pg_bin) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{pg_bin};{os.environ.get('PATH', '')}"

from apps.ai_service.engine import Engine
from apps.ai_service.main import SuggestionRequest
from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Order, Suggestion, Ticket
from apps.backend.seed import seed
from apps.backend.tickets import privacy as privacy_mod
from apps.backend.tickets.jobs import SuggestionJob, SuggestionWorker
from apps.backend.tickets.service import order_context as build_order_context
from apps.core_backend.llm.gemini import GeminiDraftClient, ORDER_CONTEXT_ALLOWED_FIELDS
from apps.core_backend.retrieval.adapter import RetrievalAdapter

OUT_DIR = Path(__file__).resolve().parent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_invariants() -> dict:
    pinned = {
        "apps/core_backend/safety.py": "45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000",
        "apps/core_backend/retrieval/adapter.py": "3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f",
        "apps/core_backend/llm/gemini.py": "c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b",
        "apps/core_backend/orchestration/pipeline_runner.py": "c981baf833a4071220b62b14043985c684dfbc307af79bc4426f18ea615765a6",
        "apps/ai_service/engine.py": "481bc7ab7fa2a7ad42ca00add79925339b138116aa2b57e233300ba3f7bc88ff",
        "apps/ai_service/main.py": "933851213299db2f051de10d6d701a94faad36c58e94623fb0ab05d8e55309cc",
        "apps/ai_service/kb-release.json": "cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804",
        "data/knowledge/approved_kb.v2.json": "f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec",
        "apps/core_backend/config/policies/intent_policy.v2.json": "8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7",
        ".local/training-cap-20261114.json": "bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922",
        ".local/ai.env": "26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87",
    }
    actual = {p: _sha256(REPO / p) for p in pinned}
    mismatches = [{"file": p, "expected": exp, "actual": actual[p]} for p, exp in pinned.items() if actual[p] != exp]
    cap = json.loads((REPO / ".local/training-cap-20261114.json").read_text(encoding="utf-8"))
    return {
        "hashes": actual,
        "mismatches": mismatches,
        "training_stopped_2_of_2": cap.get("training_stopped") is True and cap.get("additional_attempts_started") == 2,
        "passed": len(mismatches) == 0 and cap.get("training_stopped") is True,
    }


_RETRIEVER_CACHE: RetrievalAdapter | None = None
_POLICY_CACHE: dict | None = None


def _get_retriever_and_policy():
    global _RETRIEVER_CACHE, _POLICY_CACHE
    if _RETRIEVER_CACHE is None:
        release = json.loads((REPO / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
        allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
        _RETRIEVER_CACHE = RetrievalAdapter(allowed_document_versions=allowed)
    if _POLICY_CACHE is None:
        _POLICY_CACHE = json.loads((REPO / "apps/core_backend/config/policies/intent_policy.v2.json").read_text(encoding="utf-8"))
    return _RETRIEVER_CACHE, _POLICY_CACHE


def _make_engine(answer_builder, captured_bodies: list[str] | None = None, *, is_clarification: bool = False):
    """Build Engine with real RetrievalAdapter + fake HTTP MockTransport GeminiDraftClient."""
    def _handler(request: httpx.Request) -> httpx.Response:
        body_str = request.content.decode("utf-8")
        if captured_bodies is not None:
            captured_bodies.append(body_str)
        wire = json.loads(json.loads(body_str)["contents"][0]["parts"][0]["text"])
        order_sid = next((s["source_id"] for s in wire["sources"] if s.get("source_type") == "order_facts"), "S2")
        answer = answer_builder(order_sid) if callable(answer_builder) else answer_builder
        cites = []
        for s in wire["sources"]:
            sid = s["source_id"]
            if f"[{sid}]" in answer:
                cites.append(sid)
        if not cites:
            cites = [order_sid]
        raw = {
            "answerable": True,
            "answer": answer,
            "citations": cites,
            "is_clarification": is_clarification,
        }
        return httpx.Response(200, json={
            "modelVersion": "gemini-2.5-flash",
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(raw)}]}}],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20, "totalTokenCount": 70},
        })

    http = httpx.Client(transport=httpx.MockTransport(_handler), trust_env=False)
    llm = GeminiDraftClient(api_key="fake-test-key", model="gemini-2.5-flash", http_client=http)
    model = SimpleNamespace(
        predict=lambda _msg: {
            "intent": "return_policy",
            "confidence": 0.96,
            "margin": 0.80,
            "top_k": [{"intent": "return_policy", "probability": 0.96}, {"intent": "track_order", "probability": 0.04}],
            "score_kind": "calibrated_probability",
            "model_mode": "trained",
            "verified": True,
        }
    )
    retriever, policy = _get_retriever_and_policy()
    return Engine(model, retriever, llm, {"release_id": "test-rel", "model_version": "fit2-supcon-energy-boundary-v1"}, policy), llm


def _run_cases() -> list[dict]:
    cases: list[dict] = []

    # Reset spaCy handle so strict real-NER path is exercised cleanly
    privacy_mod._SPACY_NLP = None

    # 1. All 10 canonical fields + USD decimal currency normalization + Engine + Worker hydration
    full_usd = SimpleNamespace(
        payload={
            "order_id": "ORD-C-9001",
            "customer_id": "cust-c-9001",
            "customer_name": "Tran Van Secret",
            "phone": "+84909888777",
            "shipping_address": "456 Hai Ba Trung Street",
            "transaction_id": "TXN-C-9001",
            "payment_status": "Paid",
            "can_cancel": False,
            "eligible_for_return": True,
            "order_status": "delivered",
            "placed_at": "2026-10-01T07:00:00+00:00",
            "order_total": {"amount_minor": 1999, "currency": " usd "},
            "shipping_cost": {"amount_minor": 500, "currency": "usd"},
            "shipment": {
                "shipment_status": "delivered",
                "tracking_code": "TRK-C-9001",
                "carrier": "VNPost",
                "estimated_delivery_text": "Expected Friday evening",
                "estimated_delivery_at": "2026-10-03T18:00:00Z",
                "delivered_at": "2026-10-03T16:45:00.123000Z",
            },
            "refund": {
                "refund_status": "approved",
                "refund_amount": {"amount_minor": 1000, "currency": "USD"},
                "refund_requested_at": "2026-10-05",
                "expected_refund_time": "3-5 business days",
            },
        }
    )
    ctx = build_order_context(full_usd)
    env = {
        "message": "What is your return policy regarding my order dates and totals?",
        "order_context": ctx,
        "as_of": "2026-11-15T00:00:00Z",
    }
    privacy_mod.validate_egress_payload(env, require_ner=True)
    req = SuggestionRequest(**env)
    captured: list[str] = []
    eng, llm = _make_engine(
        lambda sid: (
            f"Your 19.99 USD order placed on 2026-10-01 had estimated delivery 2026-10-03 and was delivered on 2026-10-03 [{sid}]. "
            f"Your 10.00 USD refund was requested on 2026-10-05 [{sid}]."
        ),
        captured,
    )
    try:
        eng_res = eng.draft(req.model_dump())
    finally:
        llm.close()
    wire = json.loads(json.loads(captured[0])["contents"][0]["parts"][0]["text"])
    order_src_wire = [s for s in wire["sources"] if s.get("source_type") == "order_facts"][0]
    stored = []
    w_http = httpx.Client(
        transport=httpx.MockTransport(lambda req_h: httpx.Response(200, json=eng_res["analysis"] if req_h.url.path.endswith("/v1/analyses") else eng_res)),
        trust_env=False,
    )
    w = SuggestionWorker(
        database=SimpleNamespace(),
        settings=SimpleNamespace(ai_service_base_url="http://ai.local", ai_service_analysis_timeout_ms=3000, ai_service_draft_timeout_ms=11000),
        http_client=w_http,
    )
    w.store = lambda *a, **kw: stored.append(a[3])
    try:
        w.process("sug-full", "tok-full", req.model_dump())
    finally:
        w_http.close()

    hydrated_cit = stored[-1].get("draft", {}).get("citations", [{}])[0]
    excluded_absent = all(k not in ctx for k in (
        "order_id", "customer_id", "customer_name", "phone", "shipping_address",
        "transaction_id", "tracking_code", "carrier", "payment_status",
        "estimated_delivery_text", "expected_refund_time", "can_cancel", "eligible_for_return",
    ))
    secrets_absent_wire = all(s not in captured[0] for s in (
        "ORD-C-9001", "cust-c-9001", "Tran Van Secret", "+84909888777",
        "456 Hai Ba Trung", "TXN-C-9001", "TRK-C-9001", "VNPost",
        "Friday evening", "3-5 business days",
    ))
    cases.append({
        "id": "oc-10fields-usd-e2e",
        "passed": (
            list(ctx.keys()) == list(ORDER_CONTEXT_ALLOWED_FIELDS)
            and ctx["order_total"] == {"amount_minor": 1999, "currency": "USD"}
            and ctx["shipping_cost"] == {"amount_minor": 500, "currency": "USD"}
            and ctx["refund_amount"] == {"amount_minor": 1000, "currency": "USD"}
            and excluded_absent
            and secrets_absent_wire
            and order_src_wire["document_id"] == "ORDER-FACTS"
            and set(wire["order_facts"].keys()) == set(ORDER_CONTEXT_ALLOWED_FIELDS)
            and eng_res.get("status") == "draft_ready"
            and hydrated_cit.get("fields") == list(ORDER_CONTEXT_ALLOWED_FIELDS)
            and hydrated_cit.get("values") == ctx
        ),
        "eng_status": eng_res.get("status"),
        "wire_order_fact_keys": sorted(wire["order_facts"].keys()),
    })

    # 2. Root/nested None/non-dict containers + precedence (data > shipment > refund; skips None)
    empty_none = build_order_context(SimpleNamespace(payload=None))
    empty_dict = build_order_context(SimpleNamespace(payload={}))
    empty_list = build_order_context(SimpleNamespace(payload=["bad"]))
    empty_str = build_order_context(SimpleNamespace(payload="bad"))
    non_dict_nested = build_order_context(SimpleNamespace(payload={
        "order_status": "placed", "shipment": "bad", "refund": ["bad"],
    }))
    null_nested = build_order_context(SimpleNamespace(payload={
        "order_status": "placed", "shipment": None, "refund": None,
    }))
    prec = build_order_context(SimpleNamespace(payload={
        "order_status": "placed",
        "shipment_status": "shipped_root",
        "delivered_at": None,
        "shipment": {"shipment_status": "in_transit_ship", "delivered_at": "2026-10-04", "refund_status": "ship_refund"},
        "refund": {"shipment_status": "refund_ship", "delivered_at": "2026-10-09", "refund_status": "requested", "refund_requested_at": "2026-10-05"},
    }))
    cases.append({
        "id": "oc-missing-non-dict-precedence",
        "passed": (
            empty_none == {}
            and empty_dict == {}
            and empty_list == {}
            and empty_str == {}
            and non_dict_nested == {"order_status": "placed"}
            and null_nested == {"order_status": "placed"}
            and prec["shipment_status"] == "shipped_root"
            and prec["delivered_at"] == "2026-10-04"
            and prec["refund_status"] == "ship_refund"
            and prec["refund_requested_at"] == "2026-10-05"
        ),
        "precedence_observed": prec,
    })

    # 3. Malformed fields / invalid dates / money / bool / dict-in-non-money / PII / legacy keys
    poison = build_order_context(SimpleNamespace(payload={
        "order_id": "ORD-P1",
        "customer_name": "Nguyen Van B",
        "transaction_id": "TXN-P1",
        "order_status": "paid for ORD-P1 by Nguyen Van B email leak@example.com phone 0912345678",
        "placed_at": "2026-02-30",  # invalid calendar ISO date
        "estimated_delivery_at": "Tomorrow afternoon",  # prose must not pass or invent ISO
        "delivered_at": True,  # bool not str
        "refund_requested_at": "",  # blank string
        "order_total": {"amount_minor": True, "currency": "USD"},
        "shipping_cost": {"amount_minor": 100.5, "currency": "USD"},
        "shipment": {
            "tracking_code": "TRK-P1",
            "shipment_status": "tracking TRK-P1",
            "estimated_delivery_at": "2026-10-03",  # shadowed by non-None invalid root estimated_delivery_at
            "delivered_at": "2026-10-03",  # shadowed by non-None bool True at root
        },
        "refund": {
            "refund_status": "requested",
            "refund_amount": {"amount_minor": 5000, "currency": "VND", "extra": 1},
            "refund_requested_at": "2026-10-05T10:00:00Z",  # shadowed by non-None blank root ""
        },
    }))
    dict_in_str_field = build_order_context(SimpleNamespace(payload={
        "order_status": {"amount_minor": 100, "currency": "USD"},
        "shipment": {"shipment_status": 123},
        "refund": {"refund_status": True},
    }))
    jpy_ctx = build_order_context(SimpleNamespace(payload={
        "order_status": "paid",
        "order_total": {"amount_minor": 1500, "currency": "jpy"},
    }))
    valid_sibling_preserved = (
        poison.get("order_status") == "paid for [IDENTIFIER] by [IDENTIFIER] email [EMAIL] phone [PHONE_OR_NUMBER]"
        and poison.get("shipment_status") == "tracking [IDENTIFIER]"
        and poison.get("refund_status") == "requested"
        and "placed_at" not in poison
        and "estimated_delivery_at" not in poison
        and "delivered_at" not in poison
        and "refund_requested_at" not in poison
        and "order_total" not in poison
        and "shipping_cost" not in poison
        and "refund_amount" not in poison
        and dict_in_str_field == {}
        and jpy_ctx == {"order_status": "paid", "order_total": {"amount_minor": 1500, "currency": "JPY"}}
    )

    # Privacy egress blocks address or forbidden_values if they ever entered order_context
    addr_blocked = False
    try:
        privacy_mod.validate_egress_payload(
            {"message": "Hi [NAME_1]", "order_context": {"order_status": "at 123 Le Loi Street"}, "as_of": "2026-10-06T00:00:00Z"},
            require_ner=True,
        )
    except ValueError:
        addr_blocked = True

    forbidden_blocked = False
    try:
        privacy_mod.validate_egress_payload(
            {"message": "Hi [NAME_1]", "order_context": {"order_status": "An"}, "as_of": "2026-10-06T00:00:00Z"},
            require_ner=True,
            forbidden_values=("An",),
        )
    except ValueError:
        forbidden_blocked = True

    bad_envs = [
        {"order_status": "ok", "carrier": "GHN"},
        {"order_status": "ok", "payment_status": "Paid"},
        {"order_status": "ok", "can_cancel": False},
        {"order_status": "ok", "delivery_date": "2026-10-03"},
        {"order_status": "ok", "order_id": "ORD-1"},
        {"placed_at": "2026-02-30"},
        {"placed_at": 20261001},
        {"estimated_delivery_at": "Tomorrow"},
        {"delivered_at": True},
        {"order_total": {"amount_minor": True, "currency": "VND"}},
        {"order_total": {"amount_minor": -1, "currency": "VND"}},
        {"order_total": {"amount_minor": 10.5, "currency": "VND"}},
        {"order_total": {"amount_minor": 10, "currency": "VND", "extra": 1}},
        {"order_total": {"amount_minor": 10}},
        {"order_total": {"currency": "VND"}},
        {"order_total": "10 VND"},
        {"order_total": {"amount_minor": 10, "currency": "12"}},
        {"order_status": {"amount_minor": 10, "currency": "USD"}},
        {"refund_status": 123},
    ]
    egress_rejections = 0
    for bctx in bad_envs:
        b1 = b2 = False
        try:
            privacy_mod.validate_egress_payload(
                {"message": "Hi [NAME_1]", "order_context": bctx, "as_of": "2026-10-06T00:00:00Z"},
                require_ner=True,
            )
        except ValueError:
            b1 = True
        try:
            SuggestionRequest(message="Hi [NAME_1]", order_context=bctx, as_of="2026-10-06T00:00:00Z")
        except ValidationError:
            b2 = True
        if b1 and b2:
            egress_rejections += 1

    cases.append({
        "id": "oc-malformed-invalid-pii-probe",
        "passed": valid_sibling_preserved and addr_blocked and forbidden_blocked and egress_rejections == len(bad_envs),
        "poison_extracted": poison,
        "egress_rejections": f"{egress_rejections}/{len(bad_envs)}",
    })

    # 4. Non-fabrication & weakened-grounding probe (prose ETA/refund time; wrong date/amount/commitment rejected)
    prose_only = build_order_context(SimpleNamespace(payload={
        "order_status": "in_transit",
        "placed_at": "2026-10-01",
        "order_total": {"amount_minor": 200000, "currency": "VND"},
        "shipping_cost": {"amount_minor": 0, "currency": "VND"},
        "shipment": {"shipment_status": "in_transit", "estimated_delivery_text": "Expected within 3 days"},
        "refund": {"refund_status": "requested", "refund_amount": {"amount_minor": 100000, "currency": "VND"}, "expected_refund_time": "3-5 business days"},
    }))

    eng_fab1, llm_fab1 = _make_engine(lambda sid: f"Your order placed on 2026-10-01 has estimated delivery on 2026-10-04 [{sid}].")
    fab1_res = eng_fab1.draft({"message": "What is your return policy and when will it arrive?", "order_context": prose_only, "as_of": "2026-11-15T00:00:00Z"})
    llm_fab1.close()

    eng_fab2, llm_fab2 = _make_engine(lambda sid: f"Your refund was requested on 2026-10-05 [{sid}].")
    fab2_res = eng_fab2.draft({"message": "What is your return policy and when was my refund requested?", "order_context": prose_only, "as_of": "2026-11-15T00:00:00Z"})
    llm_fab2.close()

    eng_fab3, llm_fab3 = _make_engine(lambda sid: f"Your order total is 250,000 VND [{sid}].")
    fab3_res = eng_fab3.draft({"message": "What is your return policy and my order total?", "order_context": prose_only, "as_of": "2026-11-15T00:00:00Z"})
    llm_fab3.close()

    eng_fab4, llm_fab4 = _make_engine(lambda sid: f"Your order has been cancelled [{sid}].")
    fab4_res = eng_fab4.draft({"message": "What is your return policy and my order status?", "order_context": prose_only, "as_of": "2026-11-15T00:00:00Z"})
    llm_fab4.close()

    eng_ok, llm_ok = _make_engine(lambda sid: f"Your order placed on 2026-10-01 is in transit [{sid}].")
    ok_res = eng_ok.draft({"message": "What is your return policy and when was my order placed?", "order_context": prose_only, "as_of": "2026-11-15T00:00:00Z"})
    llm_ok.close()

    cases.append({
        "id": "oc-no-date-invention-grounding-strict",
        "passed": (
            "estimated_delivery_at" not in prose_only
            and "refund_requested_at" not in prose_only
            and fab1_res["status"] == "llm_unavailable" and "grounding_failed" in fab1_res["reason_codes"]
            and fab2_res["status"] == "llm_unavailable" and "grounding_failed" in fab2_res["reason_codes"]
            and fab3_res["status"] == "llm_unavailable" and "grounding_failed" in fab3_res["reason_codes"]
            and fab4_res["status"] == "llm_unavailable" and "grounding_failed" in fab4_res["reason_codes"]
            and ok_res["status"] == "draft_ready"
        ),
        "prose_only_keys": list(prose_only.keys()),
        "fab_statuses": [fab1_res["status"], fab2_res["status"], fab3_res["status"], fab4_res["status"], ok_res["status"]],
    })

    # 5. Single-field citation hydration ('field' + 'value' alongside 'fields' + 'values')
    single_ctx = {"placed_at": "2026-10-01"}
    eng_1, llm_1 = _make_engine(lambda sid: f"Your order was placed on 2026-10-01 [{sid}].")
    res_1 = eng_1.draft({"message": "What is your return policy and when was it placed?", "order_context": single_ctx, "as_of": "2026-11-15T00:00:00Z"})
    llm_1.close()
    stored_1 = []
    w1_http = httpx.Client(
        transport=httpx.MockTransport(lambda req_h: httpx.Response(200, json=res_1["analysis"] if req_h.url.path.endswith("/v1/analyses") else res_1)),
        trust_env=False,
    )
    w1 = SuggestionWorker(
        database=SimpleNamespace(),
        settings=SimpleNamespace(ai_service_base_url="http://ai.local", ai_service_analysis_timeout_ms=3000, ai_service_draft_timeout_ms=11000),
        http_client=w1_http,
    )
    w1.store = lambda *a, **kw: stored_1.append(a[3])
    try:
        w1.process("sug-single", "tok-single", {"message": "What is your return policy and when was it placed?", "order_context": single_ctx, "as_of": "2026-11-15T00:00:00Z"})
    finally:
        w1_http.close()
    cit_1 = stored_1[-1]["draft"]["citations"][0]
    expected_sid_1 = res_1["draft"]["citations"][0]["citation_id"]
    cases.append({
        "id": "oc-single-field-hydration",
        "passed": cit_1 == {
            "citation_id": expected_sid_1,
            "source_type": "order_context",
            "fields": ["placed_at"],
            "field": "placed_at",
            "values": single_ctx,
            "value": "2026-10-01",
        },
    })

    # 6. Full disposable PostgreSQL E2E (Backend create_ticket -> SuggestionJob -> Real Engine w/ fake LLM -> staff workspace)
    local = json.loads((REPO / ".local/application.json").read_text(encoding="utf-8-sig"))
    pw = local["passwords"]
    base_url = local["database_url_owner"]
    schema = f"test_oc_c_{uuid.uuid4().hex[:8]}"
    root = create_engine(base_url, hide_parameters=True)
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    eng_db = create_engine(base_url, connect_args={"options": f"-csearch_path={schema}"}, hide_parameters=True)
    db = Database(eng_db)
    db.create_schema()
    seed(db, pw)
    try:
        with db.transaction() as session:
            seeded_1001 = session.get(Order, "ORD-1001")
            seeded_1001_ctx = build_order_context(seeded_1001)
            ord_row = Order(
                order_id="ORD-C-10F",
                customer_id="demo-customer",
                payload={
                    "order_id": "ORD-C-10F",
                    "order_status": "delivered",
                    "placed_at": "2026-10-01T07:00:00Z",
                    "order_total": {"amount_minor": 1402000, "currency": "vnd"},
                    "shipping_cost": {"amount_minor": 30000, "currency": "VND"},
                    "customer_name": "Bui Thi An",
                    "phone": "+84901234567",
                    "shipping_address": "123 Le Loi Street",
                    "transaction_id": "TXN-C-10F",
                    "shipment": {
                        "shipment_status": "delivered",
                        "tracking_code": "TRK-C-10F",
                        "carrier": "GHN",
                        "estimated_delivery_at": "2026-10-03T18:00:00Z",
                        "delivered_at": "2026-10-03",
                    },
                    "refund": {
                        "refund_status": "requested",
                        "refund_amount": {"amount_minor": 400000, "currency": "VND"},
                        "refund_requested_at": "2026-10-05T09:00:00Z",
                    },
                },
            )
            session.add(ord_row)
        settings = Settings(
            database_url_app=f"{base_url}?options=-csearch_path%3D{schema}",
            database_url_owner=base_url,
            allowed_origins=["http://testserver"],
            session_cookie_secure=False,
            ai_service_base_url="http://mock-ai.local:8002",
        )
        app = create_app(settings=settings, database=db, start_worker=False)
        pg_captured: list[str] = []
        eng_pg, llm_pg = _make_engine(
            lambda sid: f"Your order placed on 2026-10-01 had delivery 2026-10-03 and refund requested 2026-10-05 [{sid}].",
            pg_captured,
        )

        def _ai_gw(req_h: httpx.Request) -> httpx.Response:
            body = json.loads(req_h.content.decode("utf-8"))
            parsed_req = SuggestionRequest(**body)
            if req_h.url.path.endswith("/v1/analyses"):
                return httpx.Response(200, json=eng_pg.analyse(parsed_req.model_dump()))
            return httpx.Response(200, json=eng_pg.draft(parsed_req.model_dump()))

        worker_http = httpx.Client(transport=httpx.MockTransport(_ai_gw), trust_env=False)
        try:
            cust = TestClient(app)
            cust.post("/v1/sessions", json={"login_name": "customer-1", "password": pw["customer"]}, headers={"origin": "http://testserver"}).raise_for_status()
            staff = TestClient(app)
            staff.post("/v1/sessions", json={"login_name": "staff-1", "password": pw["staff"]}, headers={"origin": "http://testserver"}).raise_for_status()
            privacy_mod._SPACY_NLP = None
            t_resp = cust.post("/v1/shop/tickets", json={"order_id": "ORD-C-10F", "message": "What is your return policy and when was my order delivered and refund requested?"}, headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())})
            t_resp.raise_for_status()
            tid = t_resp.json()["ticket_id"]
            with db.transaction() as session:
                t = session.get(Ticket, tid)
                job = session.get(SuggestionJob, t.current_suggestion_id)
                sid = job.suggestion_id
                tok = str(uuid.uuid4())
                job.lease_token = tok
                req_pl = dict(session.get(Suggestion, sid).request_payload)
            SuggestionWorker(db, settings, http_client=worker_http).process(sid, tok, req_pl)
            ws = staff.get(f"/v1/console/tickets/{tid}").json()
            ws_cits = ws["suggestion"]["draft"]["citations"]
            pg_secrets_absent = all(s not in pg_captured[0] for s in ("ORD-C-10F", "Bui Thi An", "+84901234567", "123 Le Loi Street", "TXN-C-10F", "TRK-C-10F", "GHN"))
            cases.append({
                "id": "oc-pg-e2e-10fields-roundtrip",
                "passed": (
                    list(req_pl["order_context"].keys()) == list(ORDER_CONTEXT_ALLOWED_FIELDS)
                    and req_pl["order_context"]["order_total"] == {"amount_minor": 1402000, "currency": "VND"}
                    and ws["suggestion"]["draft_status"] == "draft_ready"
                    and len(ws_cits) == 1
                    and ws_cits[0]["fields"] == list(ORDER_CONTEXT_ALLOWED_FIELDS)
                    and ws_cits[0]["values"] == req_pl["order_context"]
                    and pg_secrets_absent
                    and "placed_at" in seeded_1001_ctx
                    and "estimated_delivery_at" not in seeded_1001_ctx
                    and "refund_requested_at" not in seeded_1001_ctx
                ),
                "seeded_1001_keys": list(seeded_1001_ctx.keys()),
            })
        finally:
            worker_http.close()
            llm_pg.close()
    finally:
        db.engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        root.dispose()

    return cases


def main() -> None:
    t0 = time.perf_counter()
    invariants = _check_invariants()
    cases = _run_cases()
    passed = invariants["passed"] and all(c["passed"] for c in cases)
    out = {
        "verdict": "PASS" if passed else "BLOCK",
        "scope": "ORDER_CONTEXT_CONTRACT_PARITY_ONLY",
        "commit": "b94df2744d4e9d57bbbc5b4ae3b29a466d886027",
        "duration_seconds": round(time.perf_counter() - t0, 2),
        "invariants": invariants,
        "cases": cases,
    }
    (OUT_DIR / "order_context_parity_verification.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VERDICT={out['verdict']} PASSED={sum(c['passed'] for c in cases)}/{len(cases)} DUR_S={out['duration_seconds']}")


if __name__ == "__main__":
    main()
