"""Run additive zero-live-call verification for plan `c4520c1` against any target worktree.

Usage example:
  python scripts/run_guard_corrections_checks.py --target-root <worktree> --surface all
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_target_sys_path(argv: list[str]) -> Path:
    target = REPO_ROOT
    for idx, tok in enumerate(argv):
        if tok == "--target-root" and idx + 1 < len(argv):
            target = Path(argv[idx + 1]).resolve()
            break
    # Bind `apps` package to target worktree first, then place REPO_ROOT first on
    # sys.path so `pipeline.*` and `scripts.*` always resolve from this evidence repo.
    cleaned = [p for p in sys.path if Path(p or ".").resolve() not in (REPO_ROOT, target)]
    sys.path[:] = [str(target), *cleaned]
    import apps  # noqa: E402

    loaded_apps = Path(apps.__file__).resolve()
    if loaded_apps.parent != (target / "apps"):
        raise RuntimeError(f"Expected apps from {target / 'apps'}, loaded {loaded_apps}")
    sys.path[:] = [str(REPO_ROOT), str(target), *cleaned]
    return loaded_apps


LOADED_APPS_INIT = _bootstrap_target_sys_path(sys.argv[1:])

from pipeline.evaluation.fault_boundary_runner import DEFAULT_ROOT_REPO, run_fault_boundary_suite
from pipeline.evaluation.guard_corrections_verifier import (
    classify_corrected_fault_contract,
    run_b_guard_and_ownership_probes,
    verify_historic_fault_evidence_unchanged,
)
from scripts.collect_final_acceptance_evidence import compute_sha256


def _git_commit(repo_path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Guard & Fault Corrections Verification Report (`0` Live Calls)",
        "",
        f"- **Generated UTC:** `{payload['generated_at_utc']}`",
        f"- **Target Worktree:** `{payload['target_worktree']}` (`git {payload['target_git_commit']}`)",
        f"- **Loaded `apps` Package:** `{payload['loaded_apps_init']}`",
        f"- **Surface Mode:** `{payload['surface']}`",
        f"- **Historic `8f7d542` Fault Evidence Intact:** `{payload['historic_fault_evidence']['all_matched']}`",
        "",
    ]
    if "fault_suite" in payload:
        fs = payload["fault_suite"]
        lines.extend([
            "## Fault-Boundary Re-Execution (`ZeroBudgetTransport` max=0)",
            "",
            f"- **Live HTTP Attempted:** `{fs['live_http_requests_attempted']}` / `{fs['live_http_budget_max']}`",
            f"- **PG Temporary Schema Cleaned:** `{fs['pg_cleanup']['postgres_schema']}` (`absent={fs['pg_cleanup']['pg_namespace_verified_absent']}`)",
            "",
            "| Case ID | Fault | Surface / Scenario | Raw Outcome | Mapped | Privacy 404 | Strict Must-Escalate | Strict Reason | `no_draft` | Verdict |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
        ])
        for rec in fs["corrected_contract_rows"]:
            lines.append(
                f"| `{rec['case_id']}` | `{rec['fault']}` | `{rec['surface']}` / `{rec['scenario']}` | `{rec.get('raw_action', '-')}` | "
                f"`{rec.get('mapped_action', '-')}` | `{rec['privacy_intake_404_preserved']}` | "
                f"`{rec['strict_must_escalate_matched']}` | `{rec['strict_reason_any_matched']}` | "
                f"`{rec['no_draft_preserved']}` | `{rec['verdict']}` |"
            )
        lines.append("")

    if "b_probes" in payload:
        bp = payload["b_probes"]
        lines.extend([
            "## Guard Priority, Negation & `GeminiDraftClient` Boundary Probes",
            "",
            "| Probe Tag | Expectation | Initial | Final | Queue / Team | Reason Codes | `llm_called` |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :---: |",
        ])
        for row in bp["b_regression_probes"]:
            codes = ", ".join(row["reason_codes"] or []) or "-"
            lines.append(
                f"| `{row['tag']}` | `{row['expectation']}` | `{row['initial_routing_action']}` | `{row['action']}` | "
                f"`{row['target_queue']}` / `{row['requested_team']}` | `{codes}` | `{row['llm_called']}` |"
            )
        lines.extend([
            "",
            "### `final_acceptance` `product_12_answerable` Ownership Check",
            "",
        ])
        for cid, summary in bp["final_acceptance_answerable_ownership"].items():
            lines.append(
                f"- `ticket_customer_id={cid}`: `raw_draft={summary['raw_draft']}/{summary['total']}`, "
                f"`correct_intent_draft={summary['correct_intent_draft']}/{summary['total']}`, "
                f"`commerce_unauthorized_count={summary['commerce_unauthorized_count']}`"
            )
        lines.extend([
            "",
            "### `GeminiDraftClient` & Post-Generation Boundary Checks",
            "",
        ])
        gb = bp["gemini_boundary_checks"]
        vg = gb["valid_gemini_mock"]
        lines.append(
            f"- **Real `GeminiDraftClient` valid JSON mock:** `pipeline_action={vg['pipeline_action']}`, "
            f"`pipeline_has_draft={vg['pipeline_has_draft']}`, `engine_status={vg['engine_status']}`, "
            f"`confidence={vg['pipeline_confidence']}`, `margin={vg['pipeline_margin']}`, "
            f"`mock_http_calls={vg['mock_http_calls']}`"
        )
        lines.append(
            f"- **Default `GeminiDraftClient` invalid citation check:** raised `{gb['default_client_invalid_citation_error']}`"
        )
        for inj_mode, inj_row in gb["unraised_injected_llm_outputs"].items():
            lines.append(
                f"- **Injected unraised `{inj_mode}`:** `pipeline_action={inj_row['pipeline_action']}` "
                f"(`draft_present={inj_row['pipeline_draft_body_present']}`, reasons=`{inj_row['pipeline_reason_codes']}`), "
                f"`engine_status={inj_row['engine_status']}` (`draft_present={inj_row['engine_draft_present']}`, "
                f"reasons=`{inj_row['engine_reason_codes']}`)"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run zero-live-call verification for guard/fault corrections.")
    parser.add_argument("--target-root", default=str(REPO_ROOT), help="Target repo/worktree containing apps/ under test.")
    parser.add_argument("--root-repo", default=str(DEFAULT_ROOT_REPO), help="Root repo holding .local/application.json & distilbert model.")
    parser.add_argument("--surface", choices=("all", "faults", "b_probes"), default="all")
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "artifacts" / "evaluation" / "guard_corrections_20261113"),
        help="Additive output directory (must not overwrite fault_boundaries_20261113).",
    )
    args = parser.parse_args()

    target_root = Path(args.target_root).resolve()
    root_repo = Path(args.root_repo).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.name == "fault_boundaries_20261113":
        raise ValueError("Refusing to write to immutable historic directory artifacts/evaluation/fault_boundaries_20261113")
    output_dir.mkdir(parents=True, exist_ok=True)

    historic = verify_historic_fault_evidence_unchanged(REPO_ROOT)
    payload: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "target_worktree": str(target_root),
        "loaded_apps_init": str(LOADED_APPS_INIT),
        "target_git_commit": _git_commit(target_root),
        "evidence_runner_commit": _git_commit(REPO_ROOT),
        "surface": args.surface,
        "historic_fault_evidence": historic,
    }

    if args.surface in ("all", "faults"):
        raw_faults_dir = output_dir / "raw_fault_run"
        fault_suite_out = run_fault_boundary_suite(
            worktree_root=target_root,
            root_repo=root_repo,
            output_dir=raw_faults_dir,
        )
        fault_report = fault_suite_out["report"]
        all_rows = fault_report["primary_fault_results"] + fault_report["companion_fault_results"]
        corrected_rows = []
        for r in all_rows:
            c = classify_corrected_fault_contract(r)
            c["raw_action"] = (r.get("observed") or {}).get("raw_action")
            c["mapped_action"] = (r.get("observed") or {}).get("mapped_action")
            c["reason_codes"] = (r.get("observed") or {}).get("reason_codes")
            corrected_rows.append(c)
        payload["fault_suite"] = {
            "live_http_requests_attempted": fault_report["live_http_requests_attempted"],
            "live_http_budget_max": fault_report["live_http_budget_max"],
            "pg_cleanup": fault_report["pg_cleanup"],
            "summary": fault_report["summary"],
            "corrected_contract_rows": corrected_rows,
            "raw_report_path": str(raw_faults_dir / "fault_boundary_report.json"),
        }

    if args.surface in ("all", "b_probes"):
        payload["b_probes"] = run_b_guard_and_ownership_probes(
            worktree_root=target_root,
            root_repo=root_repo,
        )

    json_path = output_dir / "guard_corrections_report.json"
    md_path = output_dir / "GUARD_CORRECTIONS_REPORT.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    hashes = {
        "guard_corrections_report.json": compute_sha256(json_path),
        "GUARD_CORRECTIONS_REPORT.md": compute_sha256(md_path),
    }
    (output_dir / "report_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "b_probes"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
