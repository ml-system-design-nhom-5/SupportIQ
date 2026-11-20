#!/usr/bin/env python3
"""Freeze Task C baseline identities and independently recompute denominator metrics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.independent_baseline import build_independent_baseline_report


def render_markdown(report: dict) -> str:
    ids = report["baseline_identities"]
    srv = report["recomputed_metrics"]["serving_distilbert_supportiq"]
    rej = report["recomputed_metrics"]["rejected_supportpilot_distilbert"]
    live = report["recomputed_metrics"]["live_r3_run"]

    lines = [
        "# Task C Independent Baseline Freeze & Denominator Recomputation",
        "",
        f"- **Generated At (UTC):** `{report['generated_at']}`",
        f"- **Git HEAD:** `{ids['git']['commit']}` (dirty: `{ids['git']['is_dirty']}`)",
        f"- **Missing Frozen Files:** `{ids['missing_files']}`",
        "",
        "## 1. Key Baseline Recomputed Findings (Raw vs Correct-Intent Draft Eligibility)",
        "",
        "| Suite / Metric | Serving (`distilbert-supportiq`) | Rejected (`supportpilot-distilbert`) | Notes |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Final Acceptance Answerable (N=12) — Raw Draft-Eligible** | **{srv['final_acceptance_answerable_12']['raw_draft_eligible_count']}/12** ({srv['final_acceptance_answerable_12']['raw_draft_eligible_rate']:.2%}) | **{rej['final_acceptance_answerable_12']['raw_draft_eligible_count']}/12** ({rej['final_acceptance_answerable_12']['raw_draft_eligible_rate']:.2%}) | Serving drafts `01, 02, 08, 09, 11` |",
        f"| **Final Acceptance Answerable (N=12) — Correct-Intent Draft-Eligible** | **{srv['final_acceptance_answerable_12']['correct_intent_draft_eligible_count']}/12** ({srv['final_acceptance_answerable_12']['correct_intent_draft_eligible_rate']:.2%}) | **{rej['final_acceptance_answerable_12']['correct_intent_draft_eligible_count']}/12** ({rej['final_acceptance_answerable_12']['correct_intent_draft_eligible_rate']:.2%}) | Serving `final-case-02` predicts `return_policy` != `return_product`; candidate also drafts `final-case-12` on wrong intent `track_order` |",
        f"| **System Acceptance `draft_expected` (N=34) — Raw Draft-Eligible** | **{srv['system_acceptance_156']['draft_expected_34']['raw_draft_eligible_count']}/34** ({srv['system_acceptance_156']['draft_expected_34']['raw_draft_eligible_rate']:.2%}) | **{rej['system_acceptance_156']['draft_expected_34']['raw_draft_eligible_count']}/34** ({rej['system_acceptance_156']['draft_expected_34']['raw_draft_eligible_rate']:.2%}) | Known acceptance regression suite (not unseen holdout) |",
        f"| **System Acceptance `draft_expected` (N=34) — Correct-Intent Draft-Eligible** | **{srv['system_acceptance_156']['draft_expected_34']['correct_intent_draft_eligible_count']}/34** ({srv['system_acceptance_156']['draft_expected_34']['correct_intent_draft_eligible_rate']:.2%}) | **{rej['system_acceptance_156']['draft_expected_34']['correct_intent_draft_eligible_count']}/34** ({rej['system_acceptance_156']['draft_expected_34']['correct_intent_draft_eligible_rate']:.2%}) | Serving has {srv['system_acceptance_156']['draft_expected_34']['wrong_intent_draft_eligible_count']} wrong-intent drafts inside `draft_expected` |",
        f"| **Strict Mandatory Escalation (N=63) — Allowed Actions Match** | **{srv['system_acceptance_156']['mandatory_escalation_63']['strict_expected_actions_match_count']}/63** ({srv['system_acceptance_156']['mandatory_escalation_63']['strict_expected_actions_match_rate']:.2%}) | **{rej['system_acceptance_156']['mandatory_escalation_63']['strict_expected_actions_match_count']}/63** ({rej['system_acceptance_156']['mandatory_escalation_63']['strict_expected_actions_match_rate']:.2%}) | `abstain/manual_fallback != escalate`; serving 16 escalate + 46 manual_fallback + 1 uninjected `NOT_EXECUTED` |",
        f"| **Strict Mandatory Escalation — Real Unsafe Draft Leaks** | **{srv['system_acceptance_156']['mandatory_escalation_63']['real_unsafe_draft_leak_count']}** | **{rej['system_acceptance_156']['mandatory_escalation_63']['real_unsafe_draft_leak_count']}** ({rej['system_acceptance_156']['mandatory_escalation_63']['real_unsafe_draft_leak_case_ids']}) | Excludes pre-existing static uninjected fault `{srv['system_acceptance_156']['mandatory_escalation_63']['uninjected_fault_not_executed_case_ids']}` |",
        f"| **ML OOD (N=80) Safe Rate / Draft Leaks** | **{srv['ml_oos_80']['flagged_safe_count']}/80** (leaks: `{srv['ml_oos_80']['false_draft_eligible_count']}`) | **{rej['ml_oos_80']['flagged_safe_count']}/80** (leaks: `{rej['ml_oos_80']['false_draft_case_ids']}`) | Candidate leaks `oos-multi_intent-09` |",
        "",
        "## 2. Live R3 Run Recomputed Denominators",
        "",
        f"- **Submitted:** `{live['total_submitted']}` (`{live['http_application_cases']}` HTTP gateway + `{live['component_fixture_cases']}` component fixtures)",
        f"- **No-Auto-Send Observed (HTTP):** `{live['customer_no_auto_send_observed_http']}/{live['http_application_cases']}`",
        f"- **Answerable 12 Breakdown:** `{live['answerable_12']['pre_llm_draft_routed_count']}/12` pre-LLM draft routed (`{live['answerable_12']['correct_intent_pre_llm_draft_routed_count']}/12` correct-intent), `{live['answerable_12']['pre_llm_abstained_count']}/12` pre-LLM abstained, `{live['answerable_12']['terminal_llm_unavailable_count']}/12` timed out (`{live['answerable_12']['terminal_llm_unavailable_case_ids']}`), `{live['answerable_12']['terminal_draft_ready_count']}/12` reached `draft_ready` (`{live['answerable_12']['terminal_draft_ready_case_ids']}` — note **`final-case-02` had wrong intent `return_policy` != `return_product`, so `{live['answerable_12']['correct_intent_and_terminal_draft_ready_count']}/12` had both correct intent and live `draft_ready`**).",
        f"- **Provider Attempts Recorded:** `{live['provider_attempts_observed']['total_attempt_records']}` attempts across `{live['provider_attempts_observed']['distinct_tickets_calling_llm']}` tickets (`{live['provider_attempts_observed']['timeout_attempt_count']}` timeouts, `{live['provider_attempts_observed']['success_attempt_count']}` success).",
        "",
        "## 3. Locked Source, Policy, KB, Model, and Benchmark Checksums",
        "",
        "| Key | Path | SHA-256 | Size (B) |",
        "| :--- | :--- | :--- | ---: |",
    ]
    for key, info in ids["artifacts"].items():
        sha = f"`{info['sha256']}`" if info.get("sha256") else "`MISSING`"
        size = info.get("size_bytes") or 0
        lines.append(f"| `{key}` | `{info['path']}` | {sha} | {size} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze Task C baseline identities and recompute raw denominators.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "artifacts/evaluation/independent_baseline_20261113",
    )
    args = parser.parse_args()
    out_dir = args.out_dir if args.out_dir.is_absolute() else (REPO_ROOT / args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_independent_baseline_report(REPO_ROOT)
    (out_dir / "baseline_freeze.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "BASELINE_FREEZE_REPORT.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote baseline freeze to {out_dir}")
    srv = report["recomputed_metrics"]["serving_distilbert_supportiq"]
    print(
        f"Serving FA12 raw={srv['final_acceptance_answerable_12']['raw_draft_eligible_count']}/12, "
        f"correct_intent={srv['final_acceptance_answerable_12']['correct_intent_draft_eligible_count']}/12; "
        f"SA34 raw={srv['system_acceptance_156']['draft_expected_34']['raw_draft_eligible_count']}/34, "
        f"correct_intent={srv['system_acceptance_156']['draft_expected_34']['correct_intent_draft_eligible_count']}/34"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
