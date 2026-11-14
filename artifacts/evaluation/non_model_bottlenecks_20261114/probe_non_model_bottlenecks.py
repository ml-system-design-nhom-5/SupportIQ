"""Read-only diagnostic probe for non-model bottlenecks in SupportIQ."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
import warnings

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from apps.ai_service.engine import Engine
from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Account, Suggestion, Ticket
from apps.backend.tickets.privacy import _get_spacy_nlp, pseudonymize
from apps.backend.tickets.reports import report
from apps.core_backend.llm.gemini import prepare_llm_input
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.safety import find_draft_grounding_violation
from apps.ml_inference.app import ModelContainer
from scripts.native_runtime import configure_runtime_environment

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent


class _StubOrderLlm:
    def generate(self, message, intent, evidence, business_context=None):
        input_snap = prepare_llm_input(message, intent, evidence, business_context)
        return {
            "body": "Your order status has been checked [S2].",
            "provider": "offline_stub",
            "model": "offline-stub",
            "model_version": "offline-stub",
            "prompt_version": "grounded-v3",
            "input_snapshot": input_snap,
            "is_clarification": False,
            "usage": {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120},
            "latency_seconds": 0.0,
            "attempts": [],
        }


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (pos - lo), 2)


def main() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    results: dict = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "boundary": "read_only_local_diagnostic_zero_live_llm_calls",
    }

    # 1. Cold initialization timings
    t0 = time.perf_counter()
    model = ModelContainer()
    model.load()
    model_load_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    release = json.loads((ROOT / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(doc["document_id"], doc["version"]) for doc in release["documents"]}
    t0 = time.perf_counter()
    retriever = RetrievalAdapter(allowed_document_versions=allowed)
    retriever_load_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    t0 = time.perf_counter()
    nlp = _get_spacy_nlp()
    spacy_load_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # Check pseudonymize latency on sample customer ticket with known DB fields
    t0 = time.perf_counter()
    masked_msg, masked_map = pseudonymize(
        "Hi, I am Nguyen Van An, phone 0901234567, email an@example.com. Please check order ORD-1001.",
        {"NAME": ["Nguyen Van An"], "PHONE": ["0901234567"], "EMAIL": ["an@example.com"], "ORDER_ID": ["ORD-1001"]},
    )
    pseudonymize_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    results["cold_start"] = {
        "model_container_load_ms": model_load_ms,
        "model_ready": model.is_ready(),
        "model_trained_ready": model.is_trained_ready(),
        "retrieval_adapter_load_ms": retriever_load_ms,
        "eligible_docs": len(retriever.eligible_versions),
        "quarantined_docs": retriever.quarantined_docs,
        "spacy_en_core_web_sm_loaded": nlp is not None,
        "spacy_load_ms": spacy_load_ms,
        "pseudonymize_sample_ms": pseudonymize_ms,
        "pseudonymize_sample_tokens": list(masked_map.keys()),
    }

    # 2. Retrieval gold v2 check & stage latency + duplicate _analyse overhead
    gold_cases = json.loads((ROOT / "data/benchmarks/app_retrieval_gold_v2.json").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / "apps/core_backend/config/policies/intent_policy.v2.json").read_text(encoding="utf-8"))
    versions = {"release_id": "diag-local", "model_version": "v1.0.0"}
    engine = Engine(model, retriever, _StubOrderLlm(), versions, policy)

    # Warmup 1 call
    _ = engine.analyse({"message": "What is your return policy?", "order_context": {}, "as_of": "2026-06-15T10:00:00Z"})

    supported_recalls = []
    supported_hits = []
    ood_false_answers = 0
    ood_total = 0
    expired_false_answers = 0
    expired_total = 0
    retrieve_ms_list = []
    analyse_ms_list = []
    draft_zero_llm_ms_list = []

    for case in gold_cases:
        as_of = case.get("as_of") or "2026-06-15T10:00:00Z"
        dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        t0 = time.perf_counter()
        ret = retriever.retrieve(case["query"], case["intent"], role="agent", current_time=dt)
        retrieve_ms_list.append((time.perf_counter() - t0) * 1000.0)

        got_ids = [f"{item['document_id']}:{item['version']}" for item in ret.get("evidence", [])][:3]
        if case["slice"] == "supported":
            gold = set(case["gold_doc_ids"])
            supported_recalls.append(len(gold & set(got_ids)) / len(gold))
            supported_hits.append(1.0 if (gold & set(got_ids)) else 0.0)
        elif case["slice"] == "ood":
            ood_total += 1
            if ret["status"] == "success" and ret.get("evidence"):
                ood_false_answers += 1
        elif case["slice"] == "expired":
            expired_total += 1
            if ret["status"] == "success" and ret.get("evidence"):
                expired_false_answers += 1

        if case["slice"] == "supported":
            req = {"message": case["query"], "order_context": {}, "as_of": as_of}
            t_a = time.perf_counter()
            a_res = engine.analyse(req)
            analyse_ms_list.append((time.perf_counter() - t_a) * 1000.0)
            if a_res["routing"]["recommendation"] == "draft":
                t_d = time.perf_counter()
                _ = engine.draft(req)
                draft_zero_llm_ms_list.append((time.perf_counter() - t_d) * 1000.0)

    results["retrieval_and_duplicate_stage"] = {
        "supported_cases": len(supported_recalls),
        "supported_recall_at_3": round(sum(supported_recalls) / len(supported_recalls), 4),
        "supported_hit_at_3": round(sum(supported_hits) / len(supported_hits), 4),
        "ood_isolated_false_answer_rate": round(ood_false_answers / ood_total, 4) if ood_total else None,
        "expired_false_answer_rate": round(expired_false_answers / expired_total, 4) if expired_total else None,
        "retrieve_ms_p50": _percentile(retrieve_ms_list, 0.5),
        "retrieve_ms_p95": _percentile(retrieve_ms_list, 0.95),
        "engine_analyse_ms_p50": _percentile(analyse_ms_list, 0.5),
        "engine_analyse_ms_p95": _percentile(analyse_ms_list, 0.95),
        "engine_draft_zero_llm_overhead_ms_p50": _percentile(draft_zero_llm_ms_list, 0.5),
        "engine_draft_zero_llm_overhead_ms_p95": _percentile(draft_zero_llm_ms_list, 0.95),
        "draft_eligible_supported_count": len(draft_zero_llm_ms_list),
    }

    # 3. Order context truncation + Engine citation field mismatch check
    sample_order_context = {
        "order_status": "shipped",
        "order_total": {"amount_minor": 499000, "currency": "VND"},
        "shipping_cost": {"amount_minor": 15000, "currency": "VND"},
        "shipment_status": "delayed",
        "refund_status": "under_review",
        "refund_amount": {"amount_minor": 499000, "currency": "VND"},
    }
    sample_evidence = retriever.retrieve("Where is my package?", "track_order", role="agent")["evidence"]
    snap = prepare_llm_input("Where is my package?", "track_order", sample_evidence, sample_order_context)
    parsed_prompt = json.loads(snap["prompt"])
    s2_sources = [s for s in parsed_prompt["sources"] if s.get("source_type") == "order_facts"]

    # Engine.draft with shipment_status only vs order_status + shipment_status
    engine_ship_only = engine.draft({
        "message": "Where is my order package?",
        "intent_override": "track_order",
        "order_context": {"shipment_status": "delayed"},
        "as_of": "2026-06-15T10:00:00Z",
    })
    engine_with_order_status = engine.draft({
        "message": "Where is my order package?",
        "intent_override": "track_order",
        "order_context": sample_order_context,
        "as_of": "2026-06-15T10:00:00Z",
    })
    results["order_context_contract"] = {
        "backend_sent_fields": sorted(sample_order_context.keys()),
        "prompt_order_facts_fields": sorted(parsed_prompt["order_facts"].keys()),
        "prompt_s2_excerpt": s2_sources[0]["excerpt"] if s2_sources else None,
        "engine_draft_shipment_only_status": engine_ship_only.get("status"),
        "engine_draft_shipment_only_reasons": engine_ship_only.get("reason_codes"),
        "engine_draft_with_order_status_citations": engine_with_order_status.get("draft", {}).get("citations"),
    }

    # 4. Uncited sentence grounding false-positive probe
    policy_sources = snap["sources"][:1]
    grounding_probes = {
        "polite_hello": "Hello there.\n\nStandard return window is 30 days [S1].",
        "polite_mentions_order": "Thank you for reaching out about your order.\n\nStandard return window is 30 days [S1].",
        "polite_check_delivery": "We are happy to help check your delivery.\n\nStandard return window is 30 days [S1].",
        "polite_closing_policy": "Standard return window is 30 days [S1].\n\nPlease let us know if you have questions about this policy.",
    }
    results["grounding_uncited_probes"] = {
        name: find_draft_grounding_violation("How do I return?", body, policy_sources)
        for name, body in grounding_probes.items()
    }

    # 5. Backend middleware malformed Content-Length + reports.py telemetry check (in-memory SQLite only)
    sqlite_engine = create_engine("sqlite:///:memory:")
    db = Database(sqlite_engine)
    db.create_schema()
    settings = Settings(database_url_app="sqlite:///:memory:", session_cookie_secure=False)
    app = create_app(settings=settings, database=db, start_worker=False)
    malformed_cl_status = None
    malformed_cl_error = None
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/health/live", headers={"Content-Length": "abc"})
        malformed_cl_status = resp.status_code

    now = datetime.now(timezone.utc)
    with db.transaction() as session:
        session.add(Account(account_id="acc-1", login_name="c1", display_name="C1", role="customer", customer_id="c1", password_hash="x"))
        session.flush()
        t_created = now - timedelta(seconds=5)
        session.add(Ticket(ticket_id="TCK-1", customer_id="c1", status="open", handling_mode="assisted", created_at=t_created))
        session.flush()
        session.add(Suggestion(
            suggestion_id="sug-1",
            ticket_id="TCK-1",
            created_at=t_created,
            completed_at=now,
            payload={
                "trigger": "ticket_created",
                "analysis_status": "ready",
                "draft_status": "draft_ready",
                "llm_usage": {"input_tokens": 1700, "output_tokens": 120, "total_tokens": 1820},
                "step_latency_ms": {"analysis": 120, "draft": 1500},
            },
            request_payload={},
            pseudonym_map={},
        ))
        session.flush()
        rep_status = "ok"
        rep_data = None
        try:
            rep_data = report(session, now - timedelta(days=1), now + timedelta(days=1))
        except Exception as exc:
            rep_status = f"{type(exc).__name__}: {exc}"

    results["backend_contract_probes"] = {
        "malformed_content_length_status": malformed_cl_status,
        "report_sqlite_status": rep_status,
        "report_llm_cost_micro_usd": rep_data.get("llm_cost_micro_usd") if rep_data else None,
        "report_handling_time_ms": rep_data.get("handling_time_ms") if rep_data else None,
    }

    # 6. Read-only PostgreSQL runtime state check (no secrets printed)
    pg_info: dict = {"checked": False}
    env_file = ROOT / ".local/backend.env"
    if env_file.exists():
        configure_runtime_environment()
        db_url = None
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("SUPPORTIQ_DATABASE_URL_APP="):
                db_url = line.split("=", 1)[1].strip()
                break
        if db_url:
            pg_engine = create_engine(db_url, connect_args={"connect_timeout": 3})
            try:
                with pg_engine.connect() as conn:
                    one = conn.execute(text("SELECT 1")).scalar()
                    ticket_cnt = conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar()
                    sug_cnt = conn.execute(text("SELECT COUNT(*) FROM suggestions")).scalar()
                    pending_jobs = conn.execute(text("SELECT COUNT(*) FROM suggestion_jobs WHERE finished = false")).scalar()
                    total_jobs = conn.execute(text("SELECT COUNT(*) FROM suggestion_jobs")).scalar()
                    pg_info = {
                        "checked": True,
                        "select_1": one,
                        "tickets": ticket_cnt,
                        "suggestions": sug_cnt,
                        "pending_jobs": pending_jobs,
                        "total_jobs": total_jobs,
                    }
            except Exception as exc:
                pg_info = {"checked": True, "error_type": type(exc).__name__}
            finally:
                pg_engine.dispose()
    results["postgres_readonly"] = pg_info

    # 7. Live running local endpoints (GET only)
    live_health = {}
    for name, url in (("backend", "http://127.0.0.1:8080/health/ready"), ("ai_service", "http://127.0.0.1:8002/health/ready")):
        try:
            r = httpx.get(url, timeout=2.0, trust_env=False)
            live_health[name] = {"status_code": r.status_code, "body": r.json()}
        except Exception as exc:
            live_health[name] = {"error_type": type(exc).__name__}
    results["live_local_health"] = live_health

    out_path = OUT_DIR / "probe_results.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    main()
