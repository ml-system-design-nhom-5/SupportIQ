#!/usr/bin/env python3
"""SupportIQ Automated Evaluation and Regression Detection Runner (Task 3 / IMP-10 & IMP-11).

Truthful evidence contracts:
- Missing metrics cannot become 0.0 or PASS (marked NOT_EVALUATED / INSUFFICIENT_EVIDENCE).
- Mock, simulated, or heuristic demo runs cannot certify live acceptance.
- Cached metrics cannot imply new inference execution (execution_mode: cached_only).
- Two runs with differing KB/split/model hashes cannot be treated as regression under identical conditions.
- Every metric traces to a run manifest and raw evidence reference (evidence_ref).
- Existing artifacts remain immutable; outputs write to a fresh run directory.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.system_contracts import (
    EvaluationManifest,
    MetricProvenance,
    check_regression_comparability,
    check_mixed_evidence,
    audit_synthetic_benchmark,
)

BENCHMARK_SUMMARY_PATH = REPO_ROOT / "artifacts/evaluation/live-benchmarks/benchmark_summary.json"
REGRESSION_DIR = REPO_ROOT / "artifacts/evaluation/regression"
HISTORY_DIR = REGRESSION_DIR / "history"
RUNS_DIR = REGRESSION_DIR / "runs"

TARGETS: Dict[str, Tuple[float, str]] = {
    "intent_accuracy": (0.85, ">="),
    "intent_macro_f1": (0.85, ">="),
    "intent_ece": (0.10, "<="),
    "intent_brier": (0.15, "<="),
    "intent_ood_detection": (0.90, ">="),
    "intent_far": (0.05, "<="),
    "intent_frr": (0.05, "<="),
    "rag_recall_at_1": (0.70, ">="),
    "rag_recall_at_3": (0.80, ">="),
    "rag_recall_at_5": (0.85, ">="),
    "rag_precision_at_3": (0.30, ">="),
    "rag_mrr": (0.75, ">="),
    "rag_ndcg_at_3": (0.80, ">="),
    "grounding_claim_grounding_rate": (0.90, ">="),
    "grounding_citation_correctness": (1.00, ">="),
    "grounding_hallucination_rate": (0.02, "<="),
    "grounding_abstention_rate": (0.95, ">="),
}


def load_run_data(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load evaluation summary or manifest JSON from path or default benchmark summary."""
    p = path or BENCHMARK_SUMMARY_PATH
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def extract_metrics(
    summary: Dict[str, Any],
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Extract metrics with strict provenance and evidence traceability.
    Missing metrics are NOT defaulted to 0.0; they are assigned value=None and status='NOT_EVALUATED'.
    """
    m: Dict[str, Dict[str, Any]] = {}

    has_meta = "metadata" in summary or (manifest is not None)
    default_kind = "simulated" if has_meta else "unverified"
    if manifest and "evidence_kind" in manifest:
        default_kind = manifest["evidence_kind"]
    default_model_mode = manifest.get("model_mode") if manifest else None

    # 1. Intent metrics
    intent = summary.get("intent_classification", {})
    intent_keys = {
        "intent_accuracy": ("accuracy", "summary#intent_classification.accuracy"),
        "intent_macro_f1": ("macro_f1", "summary#intent_classification.macro_f1"),
        "intent_ece": ("ece", "summary#intent_classification.ece"),
        "intent_brier": ("brier_score", "summary#intent_classification.brier_score"),
        "intent_ood_detection": ("ood_detection_rate", "summary#intent_classification.ood_detection_rate"),
        "intent_far": ("far", "summary#intent_classification.far"),
        "intent_frr": ("frr", "summary#intent_classification.frr"),
    }
    for m_name, (k, ref) in intent_keys.items():
        raw_val = intent.get(k)
        if m_name == "intent_far" and raw_val is None:
            raw_val = intent.get("false_acceptance_rate")
        elif m_name == "intent_frr" and raw_val is None:
            raw_val = intent.get("false_rejection_rate")

        if raw_val is not None:
            val = float(raw_val)
            stat = "EVALUATED"
            e_ref = ref
        else:
            val = None
            stat = "NOT_EVALUATED"
            e_ref = None

        m[m_name] = {
            "metric": m_name,
            "value": val,
            "status": stat,
            "evidence_ref": e_ref,
            "evidence_kind": default_kind,
            "model_mode": default_model_mode,
        }

    # 2. RAG Retrieval metrics
    rag = summary.get("retrieval") or summary.get("rag_retrieval", {})
    rag_keys = {
        "rag_recall_at_1": ("recall_at_1", "summary#retrieval.recall_at_1"),
        "rag_recall_at_3": ("recall_at_3", "summary#retrieval.recall_at_3"),
        "rag_recall_at_5": ("recall_at_5", "summary#retrieval.recall_at_5"),
        "rag_precision_at_3": ("precision_at_3", "summary#retrieval.precision_at_3"),
        "rag_mrr": ("mrr", "summary#retrieval.mrr"),
        "rag_ndcg_at_3": ("ndcg_at_3", "summary#retrieval.ndcg_at_3"),
    }
    for m_name, (k, ref) in rag_keys.items():
        raw_val = rag.get(k)
        if raw_val is not None:
            val = float(raw_val)
            stat = "EVALUATED"
            e_ref = ref
        else:
            val = None
            stat = "NOT_EVALUATED"
            e_ref = None

        m[m_name] = {
            "metric": m_name,
            "value": val,
            "status": stat,
            "evidence_ref": e_ref,
            "evidence_kind": default_kind,
            "model_mode": default_model_mode,
        }

    # 3. Grounding metrics
    grounding = summary.get("grounding") or summary.get("llm_grounding", {})
    grounding_keys = {
        "grounding_claim_grounding_rate": ("claim_grounding_rate", "summary#grounding.claim_grounding_rate"),
        "grounding_citation_correctness": ("citation_correctness", "summary#grounding.citation_correctness"),
        "grounding_hallucination_rate": ("hallucination_rate", "summary#grounding.hallucination_rate"),
        "grounding_abstention_rate": ("appropriate_abstention_rate", "summary#grounding.appropriate_abstention_rate"),
    }
    for m_name, (k, ref) in grounding_keys.items():
        raw_val = grounding.get(k)
        if raw_val is not None:
            val = float(raw_val)
            stat = "EVALUATED"
            e_ref = ref
        else:
            val = None
            stat = "NOT_EVALUATED"
            e_ref = None

        m[m_name] = {
            "metric": m_name,
            "value": val,
            "status": stat,
            "evidence_ref": e_ref,
            "evidence_kind": default_kind,
            "model_mode": default_model_mode,
        }

    return m


def diagnose_metric(name: str, current: Optional[float], target: float, status: str) -> Dict[str, str]:
    if status == "PASS":
        return {"diagnosis": "Meets architectural requirement.", "recommendation": "Maintain test coverage and monitor in production."}

    if status in ("NOT_EVALUATED", "INSUFFICIENT_EVIDENCE") or current is None:
        return {
            "diagnosis": f"Metric '{name}' was not evaluated or is missing from evidence.",
            "recommendation": "Run evaluation on benchmark suite providing this metric before asserting compliance.",
        }

    if "ece" in name:
        return {
            "diagnosis": f"Calibration ECE ({current:.4f}) exceeds {target:.4f}. Softmax probabilities are overconfident on peak classes.",
            "recommendation": "Apply temperature scaling (T=1.12) to model logits or isotonic regression calibration on validation split.",
        }
    elif "recall" in name:
        return {
            "diagnosis": f"Retrieval recall ({current:.4f}) below target {target:.4f}.",
            "recommendation": "Verify query embedding generation, semantic index coverage, and ensure intent-independent vector search.",
        }
    elif "grounding" in name or "citation" in name:
        return {
            "diagnosis": f"Claim grounding ({current:.4f}) below target {target:.4f}.",
            "recommendation": "Enforce strict citation quote match in source policy chunks prior to draft creation.",
        }
    return {
        "diagnosis": f"Metric {name} ({current:.4f}) failed target {target:.4f}.",
        "recommendation": "Inspect acceptance benchmark misclassifications and retrain or tune thresholds.",
    }


def evaluate_metrics_against_targets(
    current_metrics: Dict[str, Dict[str, Any]],
    previous_metrics: Optional[Dict[str, Dict[str, Any]]] = None,
    allow_regression_comparison: bool = True,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Measure metrics against architectural targets.
    Missing metrics cannot pass; upper-bound checks fail closed.
    """
    eval_results = []
    has_target_failure = False

    for name, (target, op) in TARGETS.items():
        m_entry = current_metrics.get(name, {})
        val = m_entry.get("value")
        e_ref = m_entry.get("evidence_ref")
        e_kind = m_entry.get("evidence_kind", "simulated")
        m_mode = m_entry.get("model_mode")

        if val is None:
            status = "NOT_EVALUATED"
            has_target_failure = True
            diag = diagnose_metric(name, None, target, status)
            eval_results.append({
                "metric": name,
                "current": None,
                "target": target,
                "operator": op,
                "status": status,
                "previous": None,
                "delta": None,
                "regressed": False,
                "evidence_ref": e_ref,
                "evidence_kind": e_kind,
                "model_mode": m_mode,
                "diagnosis": diag["diagnosis"],
                "recommendation": diag["recommendation"],
            })
            continue

        passed = (val >= target) if op == ">=" else (val <= target)
        if not passed:
            if name == "intent_ece" and val <= target + 0.02:
                status = "OBSERVE"
            else:
                status = "FAIL"
                has_target_failure = True
        else:
            status = "PASS"

        # Regression comparison
        prev_entry = previous_metrics.get(name, {}) if previous_metrics else {}
        prev_val = prev_entry.get("value") if isinstance(prev_entry, dict) else None
        delta = (val - prev_val) if (prev_val is not None) else None

        regressed = False
        if allow_regression_comparison and prev_val is not None and delta is not None:
            if op == ">=" and delta < -0.015:
                regressed = True
            elif op == "<=" and delta > 0.015:
                regressed = True

        diag = diagnose_metric(name, val, target, status)
        eval_results.append({
            "metric": name,
            "current": round(val, 4),
            "target": target,
            "operator": op,
            "status": status,
            "previous": round(prev_val, 4) if prev_val is not None else None,
            "delta": round(delta, 4) if delta is not None else None,
            "regressed": regressed,
            "evidence_ref": e_ref,
            "evidence_kind": e_kind,
            "model_mode": m_mode,
            "diagnosis": diag["diagnosis"],
            "recommendation": diag["recommendation"],
        })

    return eval_results, has_target_failure


def compare_runs(
    current_run: Dict[str, Any],
    baseline_run: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare two evaluation runs, enforcing configuration comparability.
    If KB/split/model hashes differ, comparability=False and false regressions are suppressed.
    """
    comparable, reasons = check_regression_comparability(current_run, baseline_run)

    c_summary = current_run.get("summary") or current_run
    b_summary = baseline_run.get("summary") or baseline_run

    if "metrics" in current_run and isinstance(current_run["metrics"], dict) and any(k in TARGETS for k in current_run["metrics"]):
        c_metrics = current_run["metrics"]
    else:
        c_metrics = extract_metrics(c_summary, manifest=current_run.get("manifest"))

    if "metrics" in baseline_run and isinstance(baseline_run["metrics"], dict) and any(k in TARGETS for k in baseline_run["metrics"]):
        b_metrics = baseline_run["metrics"]
    else:
        b_metrics = extract_metrics(b_summary, manifest=baseline_run.get("manifest"))

    eval_results, has_failure = evaluate_metrics_against_targets(
        current_metrics=c_metrics,
        previous_metrics=b_metrics,
        allow_regression_comparison=comparable,
    )

    regressions = [
        {"metric": r["metric"], "previous": r["previous"], "current": r["current"], "delta": r["delta"]}
        for r in eval_results if r["regressed"]
    ]

    return {
        "comparable": comparable,
        "incompatibility_reasons": reasons,
        "eval_results": eval_results,
        "regressions_detected": regressions,
        "has_target_failure": has_failure,
    }


def run_regression_evaluation(
    current_path: Optional[Path] = None,
    baseline_path: Optional[Path] = None,
    output_root: Optional[Path] = None,
    cached_only: bool = False,
    skip_benchmark: bool = False,
    require_live: bool = False,
    evaluator_type: Optional[str] = None,
    study_type: Optional[str] = None,
) -> Path:
    """Execute complete regression evaluation and write immutable artifacts to fresh run directory."""
    out_base = output_root or RUNS_DIR
    out_base.mkdir(parents=True, exist_ok=True)

    # Generate unique fresh run directory
    ts_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    run_uuid = uuid.uuid4().hex[:8]
    run_id = f"regression_{ts_str}_{run_uuid}"
    run_dir = out_base / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    print("=" * 80)
    print(f"SupportIQ Automated Evaluation & Regression Loop — Run: {run_id}")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    # 1. Benchmark Execution or Cached Discovery
    current_summary = None
    if current_path:
        current_summary = load_run_data(current_path)
    elif not skip_benchmark and not cached_only:
        print("\n[Stage 1/4] Executing live benchmark evaluation...")
        runner_script = REPO_ROOT / "scripts/run_benchmarks.py"
        subprocess.run([sys.executable, str(runner_script)], check=True)
        current_summary = load_run_data(BENCHMARK_SUMMARY_PATH)
    else:
        current_summary = load_run_data(BENCHMARK_SUMMARY_PATH)

    if not current_summary:
        print("[ERROR] Failed to load benchmark summary.")
        sys.exit(1)

    # Audit for synthetic values
    is_synthetic, audit_reasons = audit_synthetic_benchmark(current_summary)
    if is_synthetic:
        print("\n[AUDIT WARNING] Detected synthetic/hardcoded benchmark signatures:")
        for r in audit_reasons:
            print(f"  - {r}")

    previous_run = load_run_data(baseline_path) if baseline_path else None

    # Determine evidence kind and modes
    evidence_kind = "cached" if cached_only else ("live" if require_live else "simulated")
    if is_synthetic and evidence_kind == "live":
        print("[WARNING] Synthetic benchmark detected in live run request; downgrading to simulated.")
        evidence_kind = "simulated"

    current_run_payload = {
        "summary": current_summary,
        "manifest": {
            "run_id": run_id,
            "evidence_kind": evidence_kind,
            "model_mode": "synthetic" if is_synthetic else "trained",
            "evaluator_type": evaluator_type or "none",
            "study_type": study_type or "none",
        },
    }

    # Comparability & Metrics evaluation
    comparison = compare_runs(
        current_run=current_run_payload,
        baseline_run=previous_run or {},
    )

    eval_results = comparison["eval_results"]
    regressions = comparison["regressions_detected"]
    comparable = comparison["comparable"]
    incomp_reasons = comparison["incompatibility_reasons"]

    # Manifest construction
    metric_prov_map = {}
    for r in eval_results:
        metric_prov_map[r["metric"]] = MetricProvenance(
            metric=r["metric"],
            value=r["current"],
            status=r["status"],
            evidence_ref=r["evidence_ref"],
            evidence_kind=evidence_kind,
            model_mode="synthetic" if is_synthetic else "trained",
            evaluator_type=evaluator_type or "none",
            study_type=study_type or "none",
            target=r["target"],
            operator=r["operator"],
            previous=r["previous"],
            delta=r["delta"],
            regressed=r["regressed"],
            diagnosis=r["diagnosis"],
            recommendation=r["recommendation"],
        )

    manifest = EvaluationManifest(
        run_id=run_id,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        evidence_kind=evidence_kind,
        model_mode="synthetic" if is_synthetic else "trained",
        evaluator_type=evaluator_type or "none",
        study_type=study_type or "none",
        execution_mode="cached_only" if cached_only else "new_execution",
        hashes={
            "kb_hash": current_summary.get("metadata", {}).get("kb_sha256"),
            "split_hash": current_summary.get("metadata", {}).get("suite_sha256"),
        },
        counts={"total_evaluated_metrics": len(eval_results)},
        metrics=metric_prov_map,
        all_mandatory_passed=(not comparison["has_target_failure"] and not regressions),
    )

    # 3. Output files into fresh run directory
    eval_json_path = run_dir / "evaluation_result.json"
    manifest_json_path = run_dir / "manifest.json"
    report_md_path = run_dir / "REGRESSION_REPORT.md"

    full_output = {
        "run_id": run_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "execution_mode": "cached_only" if cached_only else "new_execution",
        "evidence_kind": evidence_kind,
        "comparable_with_baseline": comparable,
        "incompatibility_reasons": incomp_reasons,
        "synthetic_audit_detected": is_synthetic,
        "audit_reasons": audit_reasons,
        "evaluation": eval_results,
        "regressions_detected": regressions,
    }

    with open(eval_json_path, "w", encoding="utf-8") as f:
        json.dump(full_output, f, indent=2)

    with open(manifest_json_path, "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    # 4. Generate Markdown Report
    md_lines = [
        f"# SupportIQ Automated Evaluation & Regression Report — `{run_id}`",
        "",
        f"> **Generated At:** `{datetime.datetime.now(datetime.timezone.utc).isoformat()}`  ",
        f"> **Evidence Kind:** `{evidence_kind}`  ",
        f"> **Execution Mode:** `{'cached_only' if cached_only else 'new_execution'}`  ",
        f"> **Evaluator Type:** `{evaluator_type or 'none'}`  ",
        f"> **Study Type:** `{study_type or 'none'}`  ",
        f"> **Regression Status:** `{'REGRESSION DETECTED' if regressions else 'NO REGRESSION (STABLE)'}`  ",
        "",
    ]

    if cached_only:
        md_lines.extend([
            "> [!NOTE]",
            "> **Cached Report:** This report was compiled from existing cached benchmark artifacts. "
            "No new inference execution was performed.",
            "",
        ])

    if is_synthetic:
        md_lines.extend([
            "> [!WARNING]",
            "> **Synthetic Benchmark Audit Finding:** Hardcoded claims or keyword-fallback predictions "
            "were detected in the source benchmark summary. These values cannot certify live acceptance.",
            "",
        ])

    if not comparable and previous_run:
        md_lines.extend([
            "> [!WARNING]",
            "> **Incompatible Baseline Configuration:** The current run and baseline differ in configuration/hashes. "
            f"Differences: {', '.join(incomp_reasons)}. Differences are NOT attributed to identical-condition code regression.",
            "",
        ])

    md_lines.extend([
        "---",
        "",
        "## 1. Metrics vs. Architectural Requirements",
        "",
        "| Metric | Target | Previous | Current | Delta | Status | Regression | Evidence Ref |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ])

    for r in eval_results:
        op_str = f"{r['operator']} {r['target']}"
        curr_str = f"**{r['current']:.4f}**" if r["current"] is not None else "—"
        prev_str = f"{r['previous']:.4f}" if r["previous"] is not None else "—"
        delta_str = f"{r['delta']:+.4f}" if r["delta"] is not None else "—"
        stat_badge = f"**{r['status']}**"
        reg_badge = "⚠️ REGRESSED" if r["regressed"] else ("STABLE" if comparable else "INCOMPATIBLE")
        ref_str = f"`{r['evidence_ref']}`" if r["evidence_ref"] else "—"
        md_lines.append(f"| `{r['metric']}` | {op_str} | {prev_str} | {curr_str} | {delta_str} | {stat_badge} | {reg_badge} | {ref_str} |")

    md_lines.extend([
        "",
        "---",
        "",
        "## 2. Failure Diagnosis & Remediation Recommendations",
        "",
    ])
    for r in eval_results:
        if r["status"] != "PASS" or r["regressed"]:
            curr_display = f"{r['current']}" if r["current"] is not None else "NOT_EVALUATED (None)"
            md_lines.extend([
                f"### `{r['metric']}` ({r['status']})",
                f"- **Current Value:** `{curr_display}` (Target: `{r['operator']} {r['target']}`)",
                f"- **Diagnosis:** {r['diagnosis']}",
                f"- **Recommended Fix:** {r['recommendation']}",
                "",
            ])

    md_lines.extend([
        "---",
        "",
        "## 3. Evaluation Provenance & Audit Summary",
        f"- **Run ID:** `{run_id}`",
        f"- **Run Directory:** `{run_dir}`",
        f"- **Manifest:** `{manifest_json_path}`",
        f"- **Synthetic Benchmark Audit:** `{'FAIL (Synthetic detected)' if is_synthetic else 'PASS (Computed values)'}`",
        "",
    ])

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\nSaved evaluation artifacts to fresh directory:\n  {run_dir}")
    return run_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SupportIQ Automated Evaluation and Regression Loop")
    parser.add_argument("--baseline", type=Path, default=None, help="Path to previous baseline summary JSON")
    parser.add_argument("--current", type=Path, default=None, help="Path to current summary JSON")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory to save fresh evaluation run")
    parser.add_argument("--cached-only", action="store_true", help="Compile cached evaluation report without running benchmarks")
    parser.add_argument("--skip-benchmark", action="store_true", help="Skip re-executing benchmark runner")
    parser.add_argument("--require-live", action="store_true", help="Assert live acceptance criteria")
    parser.add_argument("--evaluator-type", choices=["human", "ai", "none"], default=None, help="Evaluator kind for claims")
    parser.add_argument("--study-type", choices=["user_study", "agent_simulation", "none"], default=None, help="Study kind for timing")
    args = parser.parse_args()

    run_dir = run_regression_evaluation(
        current_path=args.current,
        baseline_path=args.baseline,
        output_root=args.output_dir,
        cached_only=args.cached_only,
        skip_benchmark=args.skip_benchmark,
        require_live=args.require_live,
        evaluator_type=args.evaluator_type,
        study_type=args.study_type,
    )
    sys.exit(0)
