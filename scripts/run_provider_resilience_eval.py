#!/usr/bin/env python3
"""Run controlled before/after provider resilience evaluation on baseline and optional B commit."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.provider_resilience_eval import (
    compare_resilience_runs,
    run_resilience_suite,
)


def _render_single_md(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"# Controlled Provider Resilience Report ({report['label']})",
        "",
        f"- **Generated At:** `{report['generated_at']}`",
        f"- **Source Commit:** `{report['source_commit']}`",
        f"- **Boundary:** {report['controlled_transport_boundary']}",
        f"- **Transient Recovery Rate:** `{s['transient_recovered_count']}/{s['transient_recoverable_schedules']}` (`{s['transient_recovery_rate']:.2%}`)",
        f"- **Budget Respected All (<=10s):** `{s['budget_respected_all']}` | **Attempt Cap Respected All (<=5s):** `{s['attempt_cap_respected_all']}`",
        f"- **Unconditional `trust_env=False`:** `{s['unconditional_trust_env_false']}` | **Latency Includes Retry Waits All:** `{s['latency_includes_retry_waits_all']}` | **429 Quota Fail-Fast:** `{s['quota_429_non_retryable_fail_fast']}` | **Storm Max Attempts:** `{s['fast_storm_max_attempts_observed']}`",
        f"- **All Attempts Persisted:** `{s['all_attempts_persisted']}` | **Zero Fabricated Totals:** `{s['zero_fabricated_totals']}` | **No-Auto-Send All:** `{s['no_auto_send_all']}`",
        f"- **Simulated Latency (s):** p50=`{s['simulated_latency_p50_seconds']}`, p95=`{s['simulated_latency_p95_seconds']}`, max=`{s['simulated_latency_max_seconds']}`",
        "",
        "| Schedule | Expected | Status | Failure | Attempts | Sim Lat / Reported Lat (s) | Sleep (s) | Wait Incl? | Usage Status | Budget<=10s |",
        "| :--- | :--- | :--- | :--- | ---: | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in report["schedules"]:
        lines.append(
            f"| `{r['schedule_id']}` | `{r['expected_if_recovered']}` | `{r['terminal_status']}` | `{r['failure_code']}` | {r['attempt_count']} | {r['simulated_elapsed_seconds']:.2f}s / {r['reported_llm_latency_seconds']:.2f}s | `{r['sleep_delays_seconds']}` | `{r['latency_includes_retry_waits']}` | `{r['usage_status']}` | `{r['budget_respected_10s']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_comparison_md(comp: dict) -> str:
    b = comp["before_summary"]
    a = comp["after_summary"]
    lines = [
        "# Before/After Controlled Provider Resilience Comparison",
        "",
        f"- **Before Commit:** `{comp['before_commit']}`",
        f"- **After Commit (B Candidate):** `{comp['after_commit']}`",
        f"- **Boundary:** {comp['controlled_transport_boundary']}",
        "",
        "## Summary Delta",
        "",
        "| Metric | Before | After |",
        "| :--- | :--- | :--- |",
        f"| **Draft-Ready Count** | {b['draft_ready_count']}/{b['total_schedules']} | {a['draft_ready_count']}/{a['total_schedules']} |",
        f"| **Transient Recovery** | {b['transient_recovered_count']}/{b['transient_recoverable_schedules']} ({b['transient_recovery_rate']:.2%}) | {a['transient_recovered_count']}/{a['transient_recoverable_schedules']} ({a['transient_recovery_rate']:.2%}) |",
        f"| **10s Budget Respected All** | `{b['budget_respected_all']}` | `{a['budget_respected_all']}` |",
        f"| **5s Attempt Cap Respected All** | `{b['attempt_cap_respected_all']}` | `{a['attempt_cap_respected_all']}` |",
        f"| **Unconditional `trust_env=False`** | `{b['unconditional_trust_env_false']}` | `{a['unconditional_trust_env_false']}` |",
        f"| **Latency Includes Retry Waits All** | `{b['latency_includes_retry_waits_all']}` | `{a['latency_includes_retry_waits_all']}` |",
        f"| **429 Daily Quota Fail-Fast** | `{b['quota_429_non_retryable_fail_fast']}` | `{a['quota_429_non_retryable_fail_fast']}` |",
        f"| **Fast 503 Storm Max Attempts** | `{b['fast_storm_max_attempts_observed']}` | `{a['fast_storm_max_attempts_observed']}` |",
        f"| **No-Auto-Send Verified All** | `{b['no_auto_send_all']}` | `{a['no_auto_send_all']}` |",
        f"| **Simulated Latency p50 / p95 / max (s)** | {b['simulated_latency_p50_seconds']} / {b['simulated_latency_p95_seconds']} / {b['simulated_latency_max_seconds']} | {a['simulated_latency_p50_seconds']} / {a['simulated_latency_p95_seconds']} / {a['simulated_latency_max_seconds']} |",
        "",
        "## Schedule-by-Schedule Comparison",
        "",
        "| Schedule | Expected | Before Status (Att / Sim / Rep) | After Status (Att / Sim / Rep) | Wait Incl? | Usage Status (B -> A) | Budget OK (B / A) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for row in comp["schedule_comparison"]:
        lines.append(
            f"| `{row['schedule_id']}` | `{row['expected_if_recovered']}` | `{row['before_status']}` ({row['before_attempts']} / {row['before_latency_s']:.2f}s / {row['before_reported_latency_s']:.2f}s) | `{row['after_status']}` ({row['after_attempts']} / {row['after_latency_s']:.2f}s / {row['after_reported_latency_s']:.2f}s) | `{row['after_latency_includes_retry_waits']}` | `{row['before_usage_status']}` -> `{row['after_usage_status']}` | `{row['before_budget_ok']}` / `{row['after_budget_ok']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _run_in_detached_worktree(
    ref: str,
    out_json: Path,
    label: str = "after_b_candidate",
    edge_contracts_json: Path | None = None,
) -> dict:
    temp_dir = Path(tempfile.mkdtemp(prefix="taskc-b-eval-"))
    worktree_dir = temp_dir / "wt"
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree_dir), ref],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        candidate_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=worktree_dir, text=True
        ).strip()
        eval_module_path = REPO_ROOT / "pipeline/evaluation/provider_resilience_eval.py"
        extra_edge = ""
        if edge_contracts_json is not None:
            extra_edge = (
                f"; edge = mod.verify_b_candidate_edge_contracts(Path(r'{str(worktree_dir)}'), source_commit=r'{candidate_sha}')"
                f"; Path(r'{str(edge_contracts_json)}').write_text(json.dumps(edge, indent=2) + '\\n', encoding='utf-8')"
            )
        eval_code = (
            "import importlib.util, json, sys; "
            f"sys.path.insert(0, r'{str(worktree_dir)}'); "
            f"spec = importlib.util.spec_from_file_location('taskc_resilience_eval', r'{str(eval_module_path)}'); "
            "mod = importlib.util.module_from_spec(spec); "
            "sys.modules['taskc_resilience_eval'] = mod; "
            "spec.loader.exec_module(mod); "
            "from pathlib import Path; "
            f"res = mod.run_resilience_suite(Path(r'{str(worktree_dir)}'), r'{label}', source_commit=r'{candidate_sha}'); "
            f"Path(r'{str(out_json)}').write_text(json.dumps(res, indent=2) + '\\n', encoding='utf-8')"
            + extra_edge
        )
        subprocess.run(
            [sys.executable, "-X", "utf8", "-c", eval_code],
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


def _write_hashes_manifest(out_dir: Path) -> None:
    import hashlib

    hashes = {}
    for p in sorted(out_dir.iterdir()):
        if p.is_file() and p.name != "report_hashes.json":
            hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (out_dir / "report_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run controlled provider resilience before/after evaluation.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "artifacts/evaluation/provider_resilience_20261113",
    )
    parser.add_argument(
        "--baseline-ref",
        default=None,
        help="Optional git ref/commit for baseline execution (defaults to current workspace).",
    )
    parser.add_argument(
        "--candidate-ref",
        default=None,
        help="Optional git ref/commit for Worker B candidate comparison.",
    )
    parser.add_argument(
        "--verify-edge-contracts",
        action="store_true",
        help="Also run targeted B edge contract checks (wait-inclusive fields, typed RetryInfo, hard quota 429 + valid header, malformed retry_after).",
    )
    args = parser.parse_args()
    out_dir = args.out_dir if args.out_dir.is_absolute() else (REPO_ROOT / args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    before_path = out_dir / "before_baseline.json"
    if args.baseline_ref:
        before_report = _run_in_detached_worktree(args.baseline_ref, before_path, label="before_baseline")
    else:
        before_report = run_resilience_suite(REPO_ROOT, label="before_baseline")
        before_path.write_text(json.dumps(before_report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "BEFORE_BASELINE_REPORT.md").write_text(_render_single_md(before_report), encoding="utf-8")

    b_sum = before_report["summary"]
    print(
        f"Baseline controlled recovery: {b_sum['transient_recovered_count']}/{b_sum['transient_recoverable_schedules']} "
        f"({b_sum['transient_recovery_rate']:.2%}), budget_ok={b_sum['budget_respected_all']}, "
        f"no_auto_send={b_sum['no_auto_send_all']}"
    )

    if args.candidate_ref:
        after_path = out_dir / "after_candidate.json"
        edge_path = (out_dir / "candidate_edge_contracts.json") if args.verify_edge_contracts else None
        after_report = _run_in_detached_worktree(
            args.candidate_ref,
            after_path,
            label="after_b_candidate",
            edge_contracts_json=edge_path,
        )
        (out_dir / "AFTER_CANDIDATE_REPORT.md").write_text(_render_single_md(after_report), encoding="utf-8")
        comp = compare_resilience_runs(before_report, after_report)
        (out_dir / "before_after_comparison.json").write_text(json.dumps(comp, indent=2) + "\n", encoding="utf-8")
        (out_dir / "BEFORE_AFTER_COMPARISON.md").write_text(_render_comparison_md(comp), encoding="utf-8")
        a_sum = after_report["summary"]
        print(
            f"Candidate ({after_report['source_commit'][:7]}) controlled recovery: "
            f"{a_sum['transient_recovered_count']}/{a_sum['transient_recoverable_schedules']} "
            f"({a_sum['transient_recovery_rate']:.2%}), budget_ok={a_sum['budget_respected_all']}, "
            f"no_auto_send={a_sum['no_auto_send_all']}"
        )
        if edge_path is not None and edge_path.exists():
            edge_data = json.loads(edge_path.read_text(encoding="utf-8"))
            print(f"Candidate ({after_report['source_commit'][:7]}) edge contracts all_passed={edge_data['all_passed']}")
        _write_hashes_manifest(out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
