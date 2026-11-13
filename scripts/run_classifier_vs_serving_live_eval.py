"""Bounded side-by-side live Gemini 3.5 Flash-Lite eval: serving (dc7af8cf) vs locked Fit2 (f695b1fe).

Ponytail-ultra helper reusing existing acceptance and provider-budget helpers:
- Reads root .env GEMINI_API_KEY in memory only; never prints or persists secrets.
- Enforces ONE shared BudgetGuardedTransport(max_requests=6) across BOTH models (0 retries).
- Disables BudgetedDraftClient internal retries (max_attempts=1) via temporary runtime wrapper.
- Uses isolated PG schema(s) + owned isolated ai_service loopback port + real BGE + active KB + demo-customer orders + identical as_of.
- Never modifies production files, root serving services, or model weights.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, Iterator, List, Optional
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm.attributes import flag_modified

WORKTREE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKTREE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKTREE_ROOT))

from scripts.native_runtime import configure_runtime_environment

configure_runtime_environment()

from apps.backend.main import create_app as create_backend_app
from apps.backend.platform.config import Settings as BackendSettings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Suggestion, Ticket
from apps.backend.seed import seed
from pipeline.evaluation.flash_lite_acceptance import (
    DEFAULT_ROOT_REPO,
    FLASH_LITE_35_MODEL,
    _build_record_from_suggestion,
    _drop_temporary_postgres_schema,
    _observe_customer_ticket,
    _poll_ticket_suggestion,
    _verify_pg_connectivity,
    load_flash_lite_private_config,
    owned_isolated_ai_service,
    summarize_flash_lite_tokens_and_cost,
    verify_serving_model_directory,
)
from pipeline.evaluation.live_provider_verification import (
    ALLOWED_GEMINI_HOST,
    BudgetGuardedTransport,
    sanitize_text,
)
from scripts.collect_final_acceptance_evidence import (
    AcceptanceEvidenceCollector,
    compute_sha256,
    resolve_database_url,
)

TARGET_CASE_IDS = ("final-case-02", "final-case-03", "final-case-10")
HARD_REMAINING_BUDGET = 6
DEFAULT_FIT2_DIR = Path(
    r"C:\Users\PC\orca\workspaces\SupportIQ\supportiq-final-routing"
    r"\artifacts\evaluation\task_a_boundary_20261113\candidate_model_fit2"
)
DEFAULT_OUTPUT_DIR = WORKTREE_ROOT / "artifacts" / "evaluation" / "classifier_vs_serving_live_20261113"


@contextmanager
def _isolated_model_and_no_retry_patch(
    calibration_manifest_path: Optional[Path],
) -> Iterator[None]:
    """Patch ModelContainer.load calibration manifest & force max_attempts=1 in memory only."""
    import apps.ai_service.main as ai_main
    import apps.ml_inference.app as ml_app

    real_load = ml_app.ModelContainer.load
    real_draft_client = ai_main.BudgetedDraftClient
    locked_cal_path = calibration_manifest_path

    def _load_with_manifest(
        self_container: Any,
        model_dir: Path = ml_app.MODEL_DIR,
        calibration_manifest_path: Optional[Path] = None,
        **kwargs: Any,
    ) -> Any:
        # Handle positional/kw calibration_manifest_path while defaulting Fit2 to its locked manifest
        eff_cal = (
            calibration_manifest_path
            if calibration_manifest_path is not None
            else locked_cal_path
        )
        return real_load(self_container, model_dir=model_dir, calibration_manifest_path=eff_cal, **kwargs)

    def _no_retry_draft_client(*args: Any, **kwargs: Any) -> Any:
        kwargs["max_attempts"] = 1
        return real_draft_client(*args, **kwargs)

    ml_app.ModelContainer.load = _load_with_manifest  # type: ignore[method-assign]
    ai_main.BudgetedDraftClient = _no_retry_draft_client  # type: ignore[assignment]
    try:
        yield
    finally:
        ml_app.ModelContainer.load = real_load  # type: ignore[method-assign]
        ai_main.BudgetedDraftClient = real_draft_client  # type: ignore[assignment]


def _build_preflight(
    *,
    worktree_root: Path,
    root_repo: Path,
    fit2_dir: Path,
    max_requests: int,
) -> tuple[Dict[str, Any], Dict[str, Any], str]:
    cfg = load_flash_lite_private_config(root_repo / ".env")
    srv_dir = root_repo / "artifacts" / "models" / "trained" / "distilbert-supportiq"
    srv_info = verify_serving_model_directory(srv_dir)

    fit2_manifest_path = fit2_dir / "calibration_manifest.json"
    if not fit2_manifest_path.exists():
        raise FileNotFoundError(f"Fit2 calibration_manifest.json missing under {fit2_dir}")
    fit2_cal = json.loads(fit2_manifest_path.read_text(encoding="utf-8"))
    fit2_info = {
        "model_dir": str(fit2_dir),
        "model_version": fit2_cal["model_version"],
        "weights_sha256": compute_sha256(fit2_dir / "model.safetensors").lower(),
        "tokenizer_sha256": compute_sha256(fit2_dir / "tokenizer.json").lower(),
        "config_sha256": compute_sha256(fit2_dir / "config.json").lower(),
        "calibration_manifest_sha256": compute_sha256(fit2_manifest_path).lower(),
        "matches_manifest_weights": compute_sha256(fit2_dir / "model.safetensors").lower()
        == fit2_cal["weights_sha256"].lower(),
    }

    owner_url, _ = resolve_database_url(str(root_repo / ".local" / "application.json"))
    pg_info = _verify_pg_connectivity(owner_url)

    cases_raw = [
        json.loads(ln)
        for ln in (worktree_root / "data/benchmarks/final_acceptance/cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    by_id = {c["id"]: c for c in cases_raw}
    target_cases = [by_id[cid] for cid in TARGET_CASE_IDS]

    preflight = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configured_provider": {
            "provider": "google_ai_studio",
            "model": FLASH_LITE_35_MODEL,
            "env_gemini_model_value": cfg["env_gemini_model_value"],
            "api_key_loaded_in_memory": bool(cfg["api_key"]),
            "configured_timeout_env": cfg.get("configured_timeout_env"),
        },
        "budget_contract": {
            "previous_global_used": 18,
            "global_authorized_total": 24,
            "remaining_global_cap": HARD_REMAINING_BUDGET,
            "requested_max_requests": max_requests,
            "hidden_retries_disabled": True,
            "budgeted_draft_client_max_attempts": 1,
            "transport_retries": 0,
            "allowed_egress_host": ALLOWED_GEMINI_HOST,
        },
        "target_cases": [
            {
                "case_id": c["id"],
                "expected_intent": c["intent"],
                "expected_action": c["expected_action"],
                "order_id": c.get("order_id"),
                "as_of": c["as_of"],
            }
            for c in target_cases
        ],
        "serving_model": srv_info,
        "candidate_fit2_model": fit2_info,
        "postgres_connectivity": pg_info,
    }
    return preflight, cfg, owner_url


def _evaluate_one_model(
    *,
    arm_name: str,
    model_dir: Path,
    calibration_manifest_path: Optional[Path],
    target_cases: List[Dict[str, Any]],
    helper_collector: AcceptanceEvidenceCollector,
    guard: BudgetGuardedTransport,
    api_key: str,
    owner_url: str,
    default_passwords: Dict[str, str],
    poll_timeout_seconds: float,
) -> Dict[str, Any]:
    schema = f"accept_cmp_{arm_name}_{uuid.uuid4().hex[:8]}"
    root_engine = create_engine(owner_url, hide_parameters=True)
    app_engine = None
    schema_created = False
    records: List[Dict[str, Any]] = []
    raw_cases: List[Dict[str, Any]] = []
    gw_info: Dict[str, Any] = {}

    try:
        with root_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True

        app_engine = create_engine(
            owner_url,
            connect_args={"options": f"-csearch_path={schema}"},
            hide_parameters=True,
        )
        database = Database(app_engine)
        database.create_schema()
        passwords = {
            role: default_passwords.get(role, uuid.uuid4().hex)
            for role in ("customer", "staff", "manager", "admin")
        }
        seed(database, passwords)

        with _isolated_model_and_no_retry_patch(calibration_manifest_path):
            with owned_isolated_ai_service(
                api_key=api_key,
                model_name=FLASH_LITE_35_MODEL,
                model_dir=model_dir,
                budget_guard=guard,
            ) as gw:
                gw_info = {
                    "base_url": gw["base_url"],
                    "health_ready": gw["health_ready"],
                    "asset_versions": gw["asset_versions"],
                    "configured_model": gw["configured_model"],
                }
                settings = BackendSettings(
                    database_url_app=owner_url,
                    database_url_owner=owner_url,
                    allowed_origins=["http://testserver"],
                    session_cookie_secure=False,
                    ai_service_base_url=gw["base_url"],
                    ai_service_analysis_timeout_ms=3000,
                    ai_service_draft_timeout_ms=11000,
                    job_poll_interval_ms=50,
                )

                # Submit with worker paused to lock identical case as_of cleanly on each suggestion
                submitted: List[tuple[Dict[str, Any], str, float]] = []
                with TestClient(create_backend_app(settings=settings, database=database, start_worker=False)) as customer:
                    customer.headers["Origin"] = "http://testserver"
                    auth_c = customer.post(
                        "/v1/sessions",
                        json={"login_name": "customer-1", "password": passwords["customer"]},
                    )
                    if auth_c.status_code != 201:
                        raise RuntimeError(f"Customer login failed ({auth_c.status_code})")

                    for c in target_cases:
                        t0 = time.perf_counter()
                        payload: Dict[str, Any] = {"message": c["query"]}
                        if c.get("order_id"):
                            payload["order_id"] = c["order_id"]
                        resp = customer.post(
                            "/v1/shop/tickets",
                            headers={"Idempotency-Key": str(uuid.uuid4())},
                            json=payload,
                        )
                        if resp.status_code != 201:
                            raise RuntimeError(f"Ticket submit failed for {c['id']}: {resp.status_code}")
                        t_id = resp.json()["ticket_id"]
                        submitted.append((c, t_id, t0))

                    with database.transaction() as db_sess:
                        for c, t_id, _ in submitted:
                            t_obj = db_sess.get(Ticket, t_id)
                            assert t_obj and t_obj.customer_id == "demo-customer"
                            s_obj = db_sess.get(Suggestion, t_obj.current_suggestion_id)
                            assert s_obj and s_obj.request_payload is not None
                            new_req = dict(s_obj.request_payload)
                            new_req["as_of"] = c["as_of"]
                            s_obj.request_payload = new_req
                            flag_modified(s_obj, "request_payload")

                # Now process SuggestionJobs with real background worker enabled
                with TestClient(create_backend_app(settings=settings, database=database, start_worker=True)) as staff, \
                     TestClient(create_backend_app(settings=settings, database=database, start_worker=False)) as customer_obs:
                    for cli, role in ((staff, "staff"), (customer_obs, "customer")):
                        cli.headers["Origin"] = "http://testserver"
                        r_auth = cli.post(
                            "/v1/sessions",
                            json={"login_name": f"{role}-1", "password": passwords[role]},
                        )
                        if r_auth.status_code != 201:
                            raise RuntimeError(f"Auth failed for {role}: {r_auth.status_code}")

                    for c, t_id, _ in submitted:
                        t_poll_start = time.perf_counter()
                        reached, suggestion_data = _poll_ticket_suggestion(
                            staff, t_id, poll_timeout_seconds=poll_timeout_seconds
                        )
                        wall_ms = round((time.perf_counter() - t_poll_start) * 1000.0, 2)
                        cust_obs = _observe_customer_ticket(customer_obs, t_id)

                        exec_ctx: Dict[str, Any] = {}
                        exec_as_of: Optional[str] = None
                        ticket_owner: Optional[str] = None
                        with database.transaction() as db_sess:
                            t_obj = db_sess.get(Ticket, t_id)
                            if t_obj:
                                ticket_owner = t_obj.customer_id
                            if t_obj and t_obj.current_suggestion_id:
                                s_obj = db_sess.get(Suggestion, t_obj.current_suggestion_id)
                                if s_obj and s_obj.request_payload:
                                    exec_ctx = dict(s_obj.request_payload.get("order_context") or {})
                                    exec_as_of = s_obj.request_payload.get("as_of")

                        rec = _build_record_from_suggestion(
                            phase="classifier_vs_serving_live",
                            case=c,
                            ticket_id=t_id,
                            wall_latency_ms=wall_ms,
                            reached_terminal=reached,
                            suggestion_data=suggestion_data,
                            cust_obs=cust_obs,
                            executed_order_context=exec_ctx,
                            executed_as_of=exec_as_of,
                            helper_collector=helper_collector,
                            secret_key=api_key,
                        )
                        raw_analysis = suggestion_data.get("analysis") or {}
                        rec["arm"] = arm_name
                        rec["ticket_owner"] = ticket_owner
                        rec["retrieved_documents"] = raw_analysis.get("documents") or []
                        rec["routing_recommendation"] = (raw_analysis.get("routing") or {}).get("recommendation")
                        rec["eligible_for_llm"] = rec["routing_recommendation"] == "draft"
                        records.append(rec)

                        raw_cases.append(
                            {
                                "arm": arm_name,
                                "case_id": c["id"],
                                "ticket_id": t_id,
                                "ticket_owner": ticket_owner,
                                "executed_as_of": exec_as_of,
                                "executed_order_context": exec_ctx,
                                "customer_observation": cust_obs,
                                "suggestion_data_sanitized": json.loads(
                                    sanitize_text(json.dumps(suggestion_data, ensure_ascii=False), api_key)
                                ),
                            }
                        )
    finally:
        if app_engine is not None:
            app_engine.dispose()
        schema_cleanup = _drop_temporary_postgres_schema(
            root_engine, schema, schema_created=schema_created
        )
        root_engine.dispose()

    all_attempts = [att for r in records for att in (r.get("attempts") or [])]
    tokens_summary = summarize_flash_lite_tokens_and_cost(all_attempts, configured_model=FLASH_LITE_35_MODEL)
    return {
        "arm": arm_name,
        "isolated_runtime": {**gw_info, **schema_cleanup},
        "summary": {
            "cases_evaluated": len(records),
            "eligible_for_llm_count": sum(1 for r in records if r["eligible_for_llm"]),
            "abstained_without_llm_count": sum(1 for r in records if r["terminal_status"] == "abstained" and r["attempt_count"] == 0),
            "escalated_without_llm_count": sum(1 for r in records if r["terminal_status"] == "escalation_recommended" and r["attempt_count"] == 0),
            "actual_llm_attempts": sum(r["attempt_count"] for r in records),
            "correct_intent_count": sum(1 for r in records if r["correct_intent"]),
            "draft_ready_count": sum(1 for r in records if r["terminal_status"] == "draft_ready"),
            "correct_intent_draft_ready_count": sum(
                1 for r in records if r["terminal_status"] == "draft_ready" and r["correct_intent"] and r["source_verification_passed"]
            ),
            "wrong_intent_draft_ready_count": sum(
                1 for r in records if r["terminal_status"] == "draft_ready" and not r["correct_intent"]
            ),
            "source_verification_passed_count": sum(1 for r in records if r["source_verification_passed"]),
        },
        "tokens_and_cost": tokens_summary,
        "records": records,
        "raw_cases": raw_cases,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Side-by-side live Gemini 3.5 Flash-Lite eval: serving vs Fit2.")
    parser.add_argument("--execute-live", action="store_true", help="Execute live LLM within max 6 remaining HTTP budget.")
    parser.add_argument("--max-requests", type=int, default=HARD_REMAINING_BUDGET, help="Hard HTTP cap (<= 6).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--root-repo", type=Path, default=DEFAULT_ROOT_REPO)
    parser.add_argument("--fit2-dir", type=Path, default=DEFAULT_FIT2_DIR)
    parser.add_argument("--poll-timeout-seconds", type=float, default=25.0)
    args = parser.parse_args(argv)

    if args.max_requests < 1 or args.max_requests > HARD_REMAINING_BUDGET:
        raise ValueError(f"--max-requests must be between 1 and {HARD_REMAINING_BUDGET}, got {args.max_requests}")

    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.chdir(WORKTREE_ROOT)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    preflight, cfg, owner_url = _build_preflight(
        worktree_root=WORKTREE_ROOT,
        root_repo=args.root_repo.resolve(),
        fit2_dir=args.fit2_dir.resolve(),
        max_requests=args.max_requests,
    )
    (args.output_dir / "preflight_and_budget.json").write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if not args.execute_live:
        print(json.dumps({"executed_live": False, "preflight": preflight}, indent=2))
        return 0

    helper_collector = AcceptanceEvidenceCollector(
        mode="live",
        suite_path=WORKTREE_ROOT / "data/benchmarks/final_acceptance/cases.jsonl",
        manifest_path=WORKTREE_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json",
        fixtures_path=WORKTREE_ROOT / "data/benchmarks/final_acceptance/injected_robustness_fixtures.json",
        paired_tasks_path=WORKTREE_ROOT / "data/benchmarks/final_acceptance/paired_agent_tasks.json",
        active_kb_path=WORKTREE_ROOT / "data/knowledge/approved_kb.v2.json",
        release_path=WORKTREE_ROOT / "apps/ai_service/kb-release.json",
        mock_orders_path=WORKTREE_ROOT / "data/knowledge/mock_orders.json",
    )
    cases_by_id = {c["id"]: c for c in helper_collector.cases}
    target_cases = [cases_by_id[cid] for cid in TARGET_CASE_IDS]
    _, default_passwords = resolve_database_url(str(args.root_repo / ".local" / "application.json"))

    guard = BudgetGuardedTransport(max_requests=args.max_requests)
    try:
        srv_dir = args.root_repo / "artifacts" / "models" / "trained" / "distilbert-supportiq"
        srv_res = _evaluate_one_model(
            arm_name="serving_dc7af8cf",
            model_dir=srv_dir,
            calibration_manifest_path=None,
            target_cases=target_cases,
            helper_collector=helper_collector,
            guard=guard,
            api_key=cfg["api_key"],
            owner_url=owner_url,
            default_passwords=default_passwords,
            poll_timeout_seconds=args.poll_timeout_seconds,
        )
        fit2_res = _evaluate_one_model(
            arm_name="fit2_f695b1fe",
            model_dir=args.fit2_dir.resolve(),
            calibration_manifest_path=args.fit2_dir.resolve() / "calibration_manifest.json",
            target_cases=target_cases,
            helper_collector=helper_collector,
            guard=guard,
            api_key=cfg["api_key"],
            owner_url=owner_url,
            default_passwords=default_passwords,
            poll_timeout_seconds=args.poll_timeout_seconds,
        )
    finally:
        guard.close()

    all_attempts = [att for arm in (srv_res, fit2_res) for r in arm["records"] for att in (r.get("attempts") or [])]
    combined_tokens = summarize_flash_lite_tokens_and_cost(all_attempts, configured_model=FLASH_LITE_35_MODEL)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope_note": (
            "Paired 3-case comparison (final-case-02, final-case-03, final-case-10) under identical "
            "owner demo-customer, case as_of, active KB, real BGE, guarded Engine, max_attempts=1, and "
            "shared BudgetGuardedTransport(max_requests=6). Not a universal benchmark claim; C candidate REJECT stands."
        ),
        "budget_accounting": {
            "previous_global_used": 18,
            "authorized_remaining_cap": args.max_requests,
            "actual_http_requests_made": guard.requests_attempted,
            "remaining_after_run": args.max_requests - guard.requests_attempted,
            "global_used_after_run": 18 + guard.requests_attempted,
            "rejected_before_network_count": guard.rejected_before_network_count,
            "transport_retries_configured": guard._retries_configured,
            "budgeted_draft_client_max_attempts": 1,
            "transport_records": guard.records,
        },
        "combined_tokens_and_cost": combined_tokens,
        "arms": {
            "serving_dc7af8cf": {k: v for k, v in srv_res.items() if k != "raw_cases"},
            "fit2_f695b1fe": {k: v for k, v in fit2_res.items() if k != "raw_cases"},
        },
    }
    raw_dump = {
        "generated_at": report["generated_at"],
        "transport_records": guard.records,
        "serving_dc7af8cf": srv_res["raw_cases"],
        "fit2_f695b1fe": fit2_res["raw_cases"],
    }

    lines = [
        "# Serving (`dc7af8cf`) vs Locked Fit2 (`f695b1fe`) Live Flash-Lite 3.5 Comparison",
        "",
        f"- **Budget:** `18/24` prior + `{guard.requests_attempted}` used now = `{18 + guard.requests_attempted}/24` (`rejected_before_network={guard.rejected_before_network_count}`, `max_attempts=1`, `retries=0`).",
        f"- **Owner & Policy Scope:** `demo-customer`, identical case `as_of`, active KB + real BGE, `CUDA_VISIBLE_DEVICES=\"\"`, C candidate **REJECT** stands (3 answerable cases only; no universal claim).",
        f"- **Tokens / Thoughts:** prompt `{combined_tokens['observed_prompt_tokens']}`, candidate `{combined_tokens['observed_candidate_tokens']}`, thoughts `{combined_tokens['observed_thought_tokens']}` (`{combined_tokens['thought_tokens_measurement_status']}`, `complete_cost_known={combined_tokens['complete_cost_known']}`).",
        "",
        "| Arm | Case | Expected | Predicted (Conf) | Rec / Terminal | Attempts | Intent OK | Source OK | Latency (ms) |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- | ---: |",
    ]
    for arm_key, arm_data in report["arms"].items():
        for r in arm_data["records"]:
            lines.append(
                f"| `{arm_key}` | `{r['case_id']}` | `{r['expected_intent']}` | "
                f"`{r['predicted_intent']}` ({r['intent_confidence']:.4f}) | "
                f"`{r['routing_recommendation']}` / `{r['terminal_status']}` | "
                f"{r['attempt_count']} | {r['correct_intent']} | {r['source_verification_passed']} | "
                f"{r['submit_to_terminal_latency_ms']} |"
            )

    (args.output_dir / "comparison_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "raw_records.json").write_text(
        json.dumps(raw_dump, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "COMPARISON_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "executed_live": True,
                "output_dir": str(args.output_dir),
                "actual_http_requests_made": guard.requests_attempted,
                "global_used_after_run": 18 + guard.requests_attempted,
                "serving_summary": srv_res["summary"],
                "fit2_summary": fit2_res["summary"],
                "thought_tokens_measurement_status": combined_tokens["thought_tokens_measurement_status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
