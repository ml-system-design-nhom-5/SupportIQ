"""Orchestrator and CLI runner for SupportIQ System Evaluation."""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.contracts import _resolve_path, validate_run_id
from pipeline.evaluation.system_contracts import (
    CaseResult,
    SystemCase,
    VerifiedSystemInputs,
    load_system_inputs,
    verify_input_snapshot,
)
from pipeline.evaluation.system_execution import (
    SystemDependencies,
    build_system_dependencies,
    execute_system_case,
    run_component_probes,
    run_oversight_scenarios,
)
from pipeline.evaluation.system_metrics import (
    aggregate_system_metrics,
    evaluate_system_gates,
)
from pipeline.evaluation.system_performance import (
    measure_system_latency,
)
from pipeline.evaluation.system_reporting import write_system_report
from pipeline.preparation.utils import compute_sha256, get_next_id
from pipeline.training.artifacts import write_json_atomic
from pipeline.training.run_training import capture_environment

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_system_evaluation(
    suite_path: Path | str,
    config_path: Path | str,
    profile: str = "mock",
    run_id: Optional[str] = None,
    output_root: Path | str = "artifacts/evaluation",
    repo_root: Path | str = REPO_ROOT,
) -> Path:
    """Execute complete end-to-end system evaluation benchmark across components,
    E2E pipeline, human oversight, latency profiling, and quality gating.
    """
    root = Path(repo_root).resolve()
    out_base = _resolve_path(str(output_root), root)

    # 1. Validate inputs and provenance
    inputs: VerifiedSystemInputs = load_system_inputs(
        repo_root=root,
        suite_path=suite_path,
        config_path=config_path,
        profile=profile,
    )

    # 2. Resolve run ID and output directory
    if run_id is None:
        run_id = get_next_id(out_base)
    else:
        validate_run_id(run_id)

    run_dir = out_base / run_id
    if run_dir.exists():
        raise EvaluationError(f"Run directory already exists at {run_dir}")

    run_dir.mkdir(parents=True, exist_ok=False)
    runtime_dir = run_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    state_file = run_dir / "run_state.json"
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write_json_atomic({"status": "running", "mode": "system", "profile": profile, "started_at": started_at}, state_file)

    deps: Optional[SystemDependencies] = None
    try:
        # 3. Environment & config snapshots
        env = capture_environment(root)
        write_json_atomic(env, run_dir / "environment.json")
        write_json_atomic(inputs.config.model_dump(), run_dir / "config.resolved.json")
        write_json_atomic(inputs.coverage, run_dir / "inputs.json")

        # 4. Build runtime dependencies
        deps = build_system_dependencies(inputs, profile=profile, runtime_dir=runtime_dir)

        # 5. Component probes
        component_results = run_component_probes(inputs, deps)
        comp_file = run_dir / "component_results.jsonl"
        with open(comp_file, "w", encoding="utf-8") as f:
            for r in component_results:
                f.write(r.model_dump_json() + "\n")

        # 6. E2E Quality evaluation
        e2e_results: List[CaseResult] = []
        for case in inputs.cases:
            attempt_id = f"e2e-{case.id}"
            res = execute_system_case(case, deps, attempt_id=attempt_id, scope="e2e")
            e2e_results.append(res)

        res_file = run_dir / "results.jsonl"
        with open(res_file, "w", encoding="utf-8") as f:
            for r in e2e_results:
                f.write(r.model_dump_json() + "\n")

        # 7. Oversight scenarios
        oversight_results = run_oversight_scenarios(deps, runtime_dir=runtime_dir)
        over_file = run_dir / "oversight_results.jsonl"
        with open(over_file, "w", encoding="utf-8") as f:
            for r in oversight_results:
                f.write(r.model_dump_json() + "\n")

        # 8. Latency measurement
        lat_results = measure_system_latency(inputs, deps)
        warm_times = [r.total_elapsed_ms / 1000.0 for r in lat_results]
        if warm_times:
            p50 = round(statistics.median(warm_times), 4)
            # Calculate p95
            sorted_times = sorted(warm_times)
            idx95 = int(round(0.95 * (len(sorted_times) - 1)))
            p95 = round(sorted_times[idx95], 4)
        else:
            p50 = "N/A"
            p95 = "N/A"

        latency_data = {
            "p50_seconds": p50,
            "warm_p95_seconds": p95,
            "requests_count": len(lat_results),
            "warmup_count": inputs.config.warmup_requests,
        }
        write_json_atomic(latency_data, run_dir / "latency.json")

        # 9. Cost & budget tracking
        cost_data = {
            "budget_exhausted": False,
            "total_cost_usd": None,
            "actual_calls": len(e2e_results),
        }
        if deps.ledger:
            cost_data.update(deps.ledger.summary())
        write_json_atomic(cost_data, run_dir / "cost.json")

        # 10. Export claims to annotate and product sessions template
        claims_file = run_dir / "claims_to_annotate.jsonl"
        with open(claims_file, "w", encoding="utf-8") as f:
            for r in e2e_results:
                if r.draft_body and r.draft_hash:
                    claim_entry = {
                        "case_id": r.case_id,
                        "draft_sha256": r.draft_hash,
                        "reviewer": None,
                        "reviewed_at": None,
                        "claims": [],
                    }
                    f.write(json.dumps(claim_entry) + "\n")

        prod_template = run_dir / "product_sessions.template.csv"
        prod_template.write_text(
            "participant_id,task_id,condition,trial_order,duration_seconds,outcome,feedback_action,draft_hash\n",
            encoding="utf-8",
        )

        # 11. Aggregate metrics and evaluate quality gates
        kb_path = inputs.source_paths.get("kb")
        kb_snapshot = None
        if kb_path and Path(kb_path).exists():
            with open(kb_path, "r", encoding="utf-8") as f:
                raw_kb = json.load(f)
            kb_snapshot = {}
            for d in raw_kb:
                d_id = d.get("doc_id") or d.get("document_id")
                ver = str(d.get("version", "1.0"))
                kb_snapshot[(d_id, ver)] = d
                if "." not in ver:
                    kb_snapshot[(d_id, f"{ver}.0")] = d

        metrics = aggregate_system_metrics(inputs.cases, e2e_results, kb_snapshot=kb_snapshot, as_of=inputs.as_of)
        metrics["latency"] = latency_data

        # Aggregate oversight scenarios
        ov_total = len(oversight_results)
        ov_passed = sum(1 for r in oversight_results if r.execution_status == "ok")
        ov_failed = ov_total - ov_passed
        metrics["oversight"] = {
            "total_scenarios": ov_total,
            "passed_scenarios": ov_passed,
            "failed_scenarios": ov_failed,
            "status": "pass" if (ov_failed == 0 and ov_total > 0) else "fail",
        }

        # Aggregate component probes
        comp_total = len(component_results)
        comp_ok = sum(1 for r in component_results if r.execution_status == "ok")
        metrics["component_probes"] = {
            "total_probes": comp_total,
            "successful_probes": comp_ok,
        }

        evidence_kind = "simulated" if profile == "mock" else "live"
        gates = evaluate_system_gates(metrics, inputs.config, evidence_kind=evidence_kind)

        write_json_atomic(metrics, run_dir / "metrics.json")

        # 12. Write report, matrix, and slice breakdown
        write_system_report(run_dir=run_dir, metrics=metrics, gates=gates, state="completed")

        # 13. Recheck input provenance snapshot
        verify_input_snapshot(inputs)

        # 14. Atomic manifest generation
        created_artifacts = [
            "config.resolved.json",
            "environment.json",
            "inputs.json",
            "results.jsonl",
            "component_results.jsonl",
            "oversight_results.jsonl",
            "metrics.json",
            "slices.csv",
            "requirements_matrix.csv",
            "latency.json",
            "cost.json",
            "claims_to_annotate.jsonl",
            "product_sessions.template.csv",
            "report.md",
        ]
        manifest_files = {}
        for fname in created_artifacts:
            fpath = run_dir / fname
            if fpath.exists():
                manifest_files[fname] = {
                    "path": fname,
                    "sha256": compute_sha256(fpath),
                }

        manifest_data = {
            "schema_version": "v1.0",
            "run_id": run_id,
            "profile": profile,
            "status": "completed",
            "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "evidence_kind": evidence_kind,
            "all_mandatory_passed": gates.get("all_mandatory_passed", False),
            "expected_draft_cases": [c.id for c in inputs.cases if c.expected.draft_expected],
            "files": manifest_files,
        }
        write_json_atomic(manifest_data, run_dir / "manifest.json")
        write_json_atomic({"status": "completed", "completed_at": manifest_data["completed_at"]}, state_file)

        return run_dir

    except Exception as exc:
        if state_file.exists():
            fail_data = {
                "status": "failed",
                "mode": "system",
                "profile": profile,
                "error": str(exc),
                "failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            write_json_atomic(fail_data, state_file)
        raise
    finally:
        if deps is not None:
            deps.close()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI orchestrator for SupportIQ System Evaluation."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="SupportIQ System Benchmark & Evaluation CLI")
    parser.add_argument("--suite", required=True, help="Path to system suite manifest JSON")
    parser.add_argument("--config", required=True, help="Path to system evaluation config JSON")
    parser.add_argument("--profile", default="mock", choices=["mock", "live"], help="Execution profile (mock or live)")
    parser.add_argument("--run-id", default=None, help="Optional run identifier")
    parser.add_argument("--output-root", default="artifacts/evaluation", help="Root output directory")
    args = parser.parse_args(argv)

    try:
        run_dir = run_system_evaluation(
            suite_path=args.suite,
            config_path=args.config,
            profile=args.profile,
            run_id=args.run_id,
            output_root=args.output_root,
        )
        print(f"=== System evaluation completed! ===")
        print(f"Run dir: {run_dir}")

        # Check gate outcomes
        man_path = run_dir / "manifest.json"
        with open(man_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        if manifest.get("all_mandatory_passed"):
            print("Status: All mandatory gates PASSED.")
            return 0
        else:
            print("Status: Incomplete or simulated evidence (acceptance gates not certified).")
            return 2
    except Exception as exc:
        print(f"System evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
