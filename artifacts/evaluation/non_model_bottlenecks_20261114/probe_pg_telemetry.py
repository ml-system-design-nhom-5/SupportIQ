"""Read-only aggregate PostgreSQL telemetry and grounding/order-citation check."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text

from apps.ai_service.engine import Engine
from apps.core_backend.llm.gemini import prepare_llm_input
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.safety import find_draft_grounding_violation
from apps.ml_inference.app import ModelContainer
from scripts.native_runtime import configure_runtime_environment

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent


class _CiteOrderLlm:
    def generate(self, message, intent, evidence, business_context=None):
        snap = prepare_llm_input(message, intent, evidence, business_context)
        sid = next(x["source_id"] for x in snap["sources"] if x["source_type"] == "order_facts")
        return {
            "body": f"Your shipment is currently delayed [{sid}].",
            "provider": "stub",
            "model": "stub",
            "model_version": "stub",
            "prompt_version": "grounded-v3",
            "input_snapshot": snap,
            "is_clarification": False,
            "usage": {},
            "latency_seconds": 0.0,
            "attempts": [],
        }


def main() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    configure_runtime_environment()
    env_path = ROOT / ".local/backend.env"
    db_url = [
        line.split("=", 1)[1].strip()
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("SUPPORTIQ_DATABASE_URL_APP=")
    ][0]
    pg_engine = create_engine(db_url, connect_args={"connect_timeout": 3})
    try:
        with pg_engine.connect() as conn:
            modes = dict(conn.execute(text("SELECT handling_mode, COUNT(*) FROM tickets GROUP BY handling_mode")).fetchall())
            statuses = dict(conn.execute(text("SELECT status, COUNT(*) FROM tickets GROUP BY status")).fetchall())
            sug_rows = conn.execute(text("SELECT payload FROM suggestions")).fetchall()
            draft_statuses = Counter((r[0] or {}).get("draft_status") for r in sug_rows)
            llm_usage_present = sum(1 for r in sug_rows if (r[0] or {}).get("llm_usage"))
            cost_present = sum(
                1 for r in sug_rows if ((r[0] or {}).get("llm_usage") or {}).get("cost_micro_usd") is not None
            )
            decisions = dict(
                conn.execute(
                    text("SELECT data->>'decision', COUNT(*) FROM audit_log_entries WHERE event_type='decision.recorded' GROUP BY 1")
                ).fetchall()
            )
            events = dict(
                conn.execute(text("SELECT event_type, COUNT(*) FROM audit_log_entries GROUP BY event_type")).fetchall()
            )
    finally:
        pg_engine.dispose()

    release = json.loads((ROOT / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(doc["document_id"], doc["version"]) for doc in release["documents"]}
    ret = RetrievalAdapter(allowed_document_versions=allowed)
    ev = ret.retrieve("What is the return time window for products sold by Tiki Trading?", "return_policy", role="agent")["evidence"]
    snap = prepare_llm_input("How do I return?", "return_policy", ev, {"order_status": "shipped", "shipment_status": "delayed"})
    order_sid = next((s["source_id"] for s in snap["sources"] if s["source_type"] == "order_facts"), None)
    pol_sources = snap["sources"][:1]
    uncited_checks = {
        "polite_hello_with_ret001": find_draft_grounding_violation(
            "Return window?", "Hello there.\n\nCustomers may return products within 30 days of delivery [S1].", pol_sources
        ),
        "polite_order_with_ret001": find_draft_grounding_violation(
            "Return window?",
            "Thank you for reaching out about your order.\n\nCustomers may return products within 30 days of delivery [S1].",
            pol_sources,
        ),
        "polite_closing_with_ret001": find_draft_grounding_violation(
            "Return window?",
            "Customers may return products within 30 days of delivery [S1].\n\nPlease let us know if you have questions about this policy.",
            pol_sources,
        ),
    }

    model = ModelContainer()
    model.load()
    policy = json.loads((ROOT / "apps/core_backend/config/policies/intent_policy.v2.json").read_text(encoding="utf-8"))
    eng_ai = Engine(model, ret, _CiteOrderLlm(), {"release_id": "diag"}, policy)
    order_cite_res = eng_ai.draft(
        {
            "message": "Where is my package?",
            "intent_override": "track_order",
            "order_context": {"order_status": "shipped", "shipment_status": "delayed"},
            "as_of": "2026-06-15T10:00:00Z",
        }
    )

    out = {
        "pg_telemetry": {
            "ticket_modes": modes,
            "ticket_statuses": statuses,
            "draft_statuses": dict(draft_statuses),
            "llm_usage_present": llm_usage_present,
            "cost_micro_usd_present": cost_present,
            "decisions": decisions,
            "audit_events": events,
        },
        "uncited_checks_on_pol_ret_001": uncited_checks,
        "order_sid_in_prompt": order_sid,
        "order_cite_res_status": order_cite_res.get("status"),
        "order_cite_res_citations": order_cite_res.get("draft", {}).get("citations"),
    }
    (OUT_DIR / "pg_and_contract_probe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
