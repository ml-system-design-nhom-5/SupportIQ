#!/usr/bin/env python3
"""Run Task C bounded live verification (4 oracle-intent cases, max 8 HTTP calls) on candidate ff0e147."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _render_md(report: dict) -> str:
    b = report["budget_accounting"]
    s = report["summary"]
    t = report["tokens_and_cost"]
    p = report["configured_provider"]
    lines = [
        "# Task C Bounded Live Oracle-Intent Provider Verification (`ff0e147`)",
        "",
        f"- **Generated At (UTC):** `{report['generated_at']}`",
        f"- **Candidate Runtime Commit:** `{report['source_commit']}`",
        f"- **Verification Scope:** `{report['verification_scope']}`",
        f"- **Boundary:** {report['scope_boundary']}",
        f"- **Provider / Model / Prompt:** `{p['provider']}` / `{p['model']}` / `{p['prompt_version']}` (`attempt_timeout={p['enforced_attempt_timeout_seconds']}s`, `budget={p['enforced_budget_seconds']}s`)",
        f"- **Preflight Budget:** `{report['preflight']['preflight_budget']}` | **Final Actual HTTP Requests:** **`{b['actual_http_requests_made']}/{b['authorized_max_http_requests']}`** | **Rejected Before Network:** `{b['rejected_before_network_count']}` | **Transport Retries:** `{b['transport_retries_configured']}`",
        f"- **Cases Executed:** `{s['cases_executed']}` | **Draft Ready:** `{s['draft_ready_count']}/{s['cases_executed']}` | **Fallback:** `{s['fallback_count']}/{s['cases_executed']}` | **No-Auto-Send All:** `{s['no_auto_send_all']}`",
        f"- **Wall Elapsed Latency (All Cases incl. Failures):** p50=`{s['wall_elapsed_p50_seconds']}s`, max=`{s['wall_elapsed_max_seconds']}s`",
        f"- **Token & Cost Status:** `{t['cost_status']}` | `complete_token_coverage={t['complete_token_coverage']}` | `attempts_missing_usage={t['attempts_missing_usage']}/{t['total_attempts_counted']}` | `observed_prompt={t['observed_prompt_tokens']}`, `observed_candidate={t['observed_candidate_tokens']}`, `observed_thought={t['observed_thought_tokens']}`, `observed_reported_total={t['observed_reported_total_tokens']}` | `conditional_observed_list_price_usd={t['conditional_observed_list_price_usd']}` (`complete_cost_known={t['complete_cost_known']}`, NOT an invoice)",
        "",
        "## Per-Case Diagnostic Results (Oracle Expected Intent + Approved KB)",
        "",
        "| Case ID | Expected Intent | Serving Raw Pred (Conf) | Terminal Status | Failure | HTTP Calls / Attempts | Wall / LLM Rep (s) | Retrieved Docs |",
        "| :--- | :--- | :--- | :--- | :--- | ---: | :--- | :--- |",
    ]
    for c in report["cases"]:
        docs = ", ".join(f"`{d['document_id']}:{d['version']}`" for d in c["retrieved_sources"])
        lines.append(
            f"| `{c['case_id']}` | `{c['expected_intent']}` | `{c['serving_raw_prediction']}` ({c['serving_raw_confidence']:.4f}) | `{c['terminal_status']}` | `{c['failure_code']}` | {c['http_requests_this_case']} / {c['attempt_count']} | {c['wall_elapsed_seconds']:.2f}s / {c['reported_llm_latency_seconds']:.2f}s | {docs} |"
        )
    lines.append("")
    lines.append("## Per-Attempt Telemetry")
    lines.append("")
    lines.append("| Case ID | Attempt # | Status | HTTP | Stage | Exception Category | Latency (s) | Prompt / Cand / Total Tokens |")
    lines.append("| :--- | ---: | :--- | ---: | :--- | :--- | ---: | :--- |")
    for c in report["cases"]:
        for att in c["attempts"]:
            u = att.get("usage") or {}
            tok = f"{u.get('promptTokenCount')} / {u.get('candidatesTokenCount')} / {u.get('totalTokenCount')}"
            lines.append(
                f"| `{c['case_id']}` | {att.get('attempt_index')} | `{att.get('status')}` | `{att.get('http_status')}` | `{att.get('stage')}` | `{att.get('exception_category')}` | {att.get('latency_seconds')} | `{tok}` |"
            )
    lines.append("")
    return "\n".join(lines)


def _execute_in_detached_worktree(
    candidate_ref: str,
    model_dir: Path,
    private_env_path: Path,
    out_json: Path,
    *,
    execute_live: bool,
) -> dict:
    temp_dir = Path(tempfile.mkdtemp(prefix="taskc-live-eval-"))
    worktree_dir = temp_dir / "wt"
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree_dir), candidate_ref],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        candidate_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=worktree_dir, text=True
        ).strip()
        mod_path = REPO_ROOT / "pipeline/evaluation/live_provider_verification.py"
        code = (
            "import importlib.util, json, sys; "
            f"sys.path.insert(0, r'{str(worktree_dir)}'); "
            f"spec = importlib.util.spec_from_file_location('taskc_live_verify', r'{str(mod_path)}'); "
            "mod = importlib.util.module_from_spec(spec); "
            "sys.modules['taskc_live_verify'] = mod; "
            "spec.loader.exec_module(mod); "
            "from pathlib import Path; "
            f"res = mod.run_bounded_live_verification(Path(r'{str(worktree_dir)}'), Path(r'{str(model_dir)}'), Path(r'{str(private_env_path)}'), execute_live={execute_live!r}, source_commit=r'{candidate_sha}'); "
            f"Path(r'{str(out_json)}').write_text(json.dumps(res, indent=2, ensure_ascii=False) + '\\n', encoding='utf-8')"
        )
        subprocess.run(
            [sys.executable, "-X", "utf8", "-c", code],
            cwd=worktree_dir,
            check=True,
        )
        return json.loads(out_json.read_text(encoding="utf-8"))
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded Task C live provider verification (4 cases, max 8 requests).")
    parser.add_argument("--candidate-ref", default="ff0e147")
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(r"F:\Năm 3\SD\project\SupportIQ\artifacts\models\trained\distilbert-supportiq"),
    )
    parser.add_argument(
        "--private-env",
        type=Path,
        default=Path(r"F:\Năm 3\SD\project\SupportIQ\.env"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "artifacts/evaluation/live_ff0e147_oracle_20261113",
    )
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Actually issue bounded live HTTP calls (max 8). Omit for 0-call offline preflight dry run.",
    )
    args = parser.parse_args()

    out_dir = args.out_dir if args.out_dir.is_absolute() else (REPO_ROOT / args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_json = out_dir / ("live_verification.json" if args.execute_live else "dry_run_preflight.json")

    report = _execute_in_detached_worktree(
        args.candidate_ref,
        args.model_dir,
        args.private_env,
        raw_json,
        execute_live=args.execute_live,
    )
    if args.execute_live:
        (out_dir / "LIVE_VERIFICATION_REPORT.md").write_text(_render_md(report), encoding="utf-8")
        hashes = {}
        for p in sorted(out_dir.iterdir()):
            if p.is_file() and p.name != "report_hashes.json":
                hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        (out_dir / "report_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
        b = report["budget_accounting"]
        s = report["summary"]
        print(
            f"Final HTTP requests: {b['actual_http_requests_made']}/{b['authorized_max_http_requests']} | "
            f"draft_ready={s['draft_ready_count']}/{s['cases_executed']} | no_auto_send={s['no_auto_send_all']}"
        )
    else:
        print(f"Dry-run completed cleanly: final_http_requests={report['final_http_requests']}/{report['preflight']['max_requests']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
