#!/usr/bin/env python3
"""SupportIQ Automated Evaluation and Regression Detection Runner (Task 3 / IMP-10 & IMP-11).

Truthful evidence contracts:
- Missing metrics cannot become 0.0 or PASS (marked NOT_EVALUATED / INSUFFICIENT_EVIDENCE).
- Metric values that are NaN, inf, bool, or out-of-range are strictly rejected.
- Mock, simulated, or heuristic demo runs cannot certify live acceptance.
- Cached metrics cannot imply new inference execution (execution_mode: cached_only).
- Read-only paths (--current, --skip-benchmark) are strictly labeled cached/no new inference.
- --require-live is an assertive validation gate that fails non-zero if live criteria are unmet;
  it never authorizes relabeling unauthenticated summaries as live or trained.
- Absence of synthetic audit signatures is NOT evidence authentication.
- Two runs with differing or missing KB/split/model hashes cannot be treated as regression under identical conditions.
- Every metric traces to a run manifest and raw evidence reference (evidence_ref pointing to saved file).
- Existing artifacts remain immutable; outputs write to a fresh run directory.
- CLI exits non-zero if requested gates, targets, or live certification fail.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import platform
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


def compute_sha256(path: Path) -> str:
    """Compute uppercase SHA-256 for a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


def get_git_commit(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """Capture current git commit sha or environment fallback."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        commit = res.stdout.strip()
        if commit:
            return commit
    except Exception:
        pass
    return os.environ.get("GIT_COMMIT")


def validate_metric_value(raw_val: Any) -> Optional[float]:
    """Validate numeric metric: reject bool, None, NaN, inf, or out-of-range numbers."""
    if isinstance(raw_val, bool) or raw_val is None:
        return None
    try:
        f_val = float(raw_val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f_val) or math.isinf(f_val):
        return None
    if f_val < 0.0 or f_val > 1.0:
        return None
    return f_val


def load_run_data(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load evaluation summary or manifest JSON from path or default benchmark summary,
    preserving full nested provenance (hashes, manifest, metadata, files).
    """
    p = path or BENCHMARK_SUMMARY_PATH
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    
    if not p.exists():
        return None

    target_file = p
    manifest_data = None

    if p.is_dir():
        # Directory passed: check for manifest.json and summary files
        m_file = p / "manifest.json"
        if m_file.exists():
            try:
                with open(m_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
            except Exception:
                pass
        
        candidates = ["source_summary.json", "benchmark_summary.json", "evaluation_result.json", "metrics.json"]
        found = None
        for c in candidates:
            cand = p / c
            if cand.exists():
                found = cand
                break
        if not found:
            return {"manifest": manifest_data} if manifest_data else None
        target_file = found
    else:
        # File passed: check if sibling manifest.json exists
        sibling_m = p.parent / "manifest.json"
        if sibling_m.exists():
            try:
                with open(sibling_m, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
            except Exception:
                pass

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception:
        return None

    # Merge nested provenance
    out_payload: Dict[str, Any] = {}
    if isinstance(raw_data, dict):
        if "summary" in raw_data:
            out_payload["summary"] = raw_data["summary"]
            out_payload["manifest"] = raw_data.get("manifest") or manifest_data
            out_payload["hashes"] = raw_data.get("hashes", {})
        else:
            out_payload["summary"] = raw_data
            out_payload["manifest"] = manifest_data
            meta = raw_data.get("metadata", {})
            out_payload["hashes"] = {
                "kb_hash": meta.get("kb_sha256") or meta.get("kb_hash"),
                "split_hash": meta.get("suite_sha256") or meta.get("split_hash"),
                "model_hash": meta.get("weights_sha256") or meta.get("model_hash"),
            }
        
        if manifest_data and isinstance(manifest_data, dict):
            out_payload["hashes"].update(manifest_data.get("hashes", {}))
            if "evidence_kind" not in out_payload:
                out_payload["evidence_kind"] = manifest_data.get("evidence_kind")
            if "model_mode" not in out_payload:
                out_payload["model_mode"] = manifest_data.get("model_mode")

    return out_payload


def extract_metrics(
    summary: Dict[str, Any],
    manifest: Optional[Dict[str, Any]] = None,
    source_ref_name: str = "source_summary.json",
) -> Dict[str, Dict[str, Any]]:
    """Extract metrics with strict provenance and evidence traceability.
    Missing, NaN, inf, bool, or out-of-range metrics are NOT defaulted to 0.0;
    they are assigned value=None and status='NOT_EVALUATED'.
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
        "intent_accuracy": ("accuracy", f"{source_ref_name}#intent_classification.accuracy"),
        "intent_macro_f1": ("macro_f1", f"{source_ref_name}#intent_classification.macro_f1"),
        "intent_ece": ("ece", f"{source_ref_name}#intent_classification.ece"),
        "intent_brier": ("brier_score", f"{source_ref_name}#intent_classification.brier_score"),
        "intent_ood_detection": ("ood_detection_rate", f"{source_ref_name}#intent_classification.ood_detection_rate"),
        "intent_far": ("far", f"{source_ref_name}#intent_classification.far"),
        "intent_frr": ("frr", f"{source_ref_name}#intent_classification.frr"),
    }
    for m_name, (k, ref) in intent_keys.items():
        raw_val = intent.get(k)
        if m_name == "intent_far" and raw_val is None:
            raw_val = intent.get("false_acceptance_rate")
        elif m_name == "intent_frr" and raw_val is None:
            raw_val = intent.get("false_rejection_rate")

        val = validate_metric_value(raw_val)
        stat = "EVALUATED" if val is not None else "NOT_EVALUATED"
        e_ref = ref if val is not None else None

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
        "rag_recall_at_1": ("recall_at_1", f"{source_ref_name}#retrieval.recall_at_1"),
        "rag_recall_at_3": ("recall_at_3", f"{source_ref_name}#retrieval.recall_at_3"),
        "rag_recall_at_5": ("recall_at_5", f"{source_ref_name}#retrieval.recall_at_5"),
        "rag_precision_at_3": ("precision_at_3", f"{source_ref_name}#retrieval.precision_at_3"),
        "rag_mrr": ("mrr", f"{source_ref_name}#retrieval.mrr"),
        "rag_ndcg_at_3": ("ndcg_at_3", f"{source_ref_name}#retrieval.ndcg_at_3"),
    }
    for m_name, (k, ref) in rag_keys.items():
        raw_val = rag.get(k)
        val = validate_metric_value(raw_val)
        stat = "EVALUATED" if val is not None else "NOT_EVALUATED"
        e_ref = ref if val is not None else None

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
        "grounding_claim_grounding_rate": ("claim_grounding_rate", f"{source_ref_name}#grounding.claim_grounding_rate"),
        "grounding_citation_correctness": ("citation_correctness", f"{source_ref_name}#grounding.citation_correctness"),
        "grounding_hallucination_rate": ("hallucination_rate", f"{source_ref_name}#grounding.hallucination_rate"),
        "grounding_abstention_rate": ("appropriate_abstention_rate", f"{source_ref_name}#grounding.appropriate_abstention_rate"),
    }
    for m_name, (k, ref) in grounding_keys.items():
        raw_val = grounding.get(k)
        val = validate_metric_value(raw_val)
        stat = "EVALUATED" if val is not None else "NOT_EVALUATED"
        e_ref = ref if val is not None else None

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
            "diagnosis": f"Metric '{name}' was not evaluated, invalid, or is missing from evidence.",
            "recommendation": "Run evaluation on benchmark suite providing this metric before asserting compliance.",
        }

    if "ece" in name:
        return {
            "diagnosis": f"Calibration ECE ({current:.4f}) exceeds target {target:.4f}. Softmax probabilities are overconfident on peak classes.",
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
    Missing or invalid metrics cannot pass; upper-bound checks fail closed.
    ECE over target cannot pass mandatory requirements via OBSERVE.
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
            # NOTE: ECE over target is still a target gap; mandatory passed cannot be True
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
    """Compare two evaluation runs, strictly enforcing configuration comparability.
    If KB/split/model hashes differ or are absent, comparability=False and regressions are suppressed.
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
) -> Tuple[Path, bool]:
    """Execute complete regression evaluation and write immutable artifacts to fresh run directory.
    Returns (run_dir, success_flag).
    """
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
    is_read_only = (current_path is not None) or skip_benchmark or cached_only
    current_run_loaded = None
    if current_path:
        current_run_loaded = load_run_data(current_path)
    elif not skip_benchmark and not cached_only:
        print("\n[Stage 1/4] Executing live benchmark evaluation...")
        runner_script = REPO_ROOT / "scripts/run_benchmarks.py"
        subprocess.run([sys.executable, str(runner_script)], check=True)
        current_run_loaded = load_run_data(BENCHMARK_SUMMARY_PATH)
    else:
        current_run_loaded = load_run_data(BENCHMARK_SUMMARY_PATH)

    if not current_run_loaded or not current_run_loaded.get("summary"):
        print("[ERROR] Failed to load benchmark summary.")
        sys.exit(1)

    current_summary = current_run_loaded["summary"]
    source_manifest = current_run_loaded.get("manifest") or {}
    source_hashes = current_run_loaded.get("hashes", {})

    # Snapshot source summary into fresh run directory
    source_snapshot_name = "source_summary.json"
    source_snapshot_file = run_dir / source_snapshot_name
    with open(source_snapshot_file, "w", encoding="utf-8") as f:
        json.dump(current_summary, f, indent=2)
    source_snapshot_sha256 = compute_sha256(source_snapshot_file)

    # Audit for synthetic values
    is_synthetic, audit_reasons = audit_synthetic_benchmark(current_summary)
    if is_synthetic:
        print("\n[AUDIT WARNING] Detected synthetic/hardcoded benchmark signatures:")
        for r in audit_reasons:
            print(f"  - {r}")

    # Determine execution mode and evidence kind
    if is_read_only:
        execution_mode = "cached_only"
        # Reading existing files is cached; never infer live
        evidence_kind = "cached" if not is_synthetic else "simulated"
    else:
        execution_mode = "new_execution"
        evidence_kind = "simulated" if is_synthetic else "live"

    # Model mode: never infer 'trained' from absence of synthetic signature
    model_mode = source_manifest.get("model_mode")
    if not model_mode:
        model_mode = "synthetic" if is_synthetic else "unverified"

    # Capture real environment & git commit
    git_commit = get_git_commit(REPO_ROOT)
    env_data = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
    }
    cfg_data = {
        "targets": {k: {"threshold": v[0], "op": v[1]} for k, v in TARGETS.items()},
        "tolerance": 0.015,
        "evaluator_type": evaluator_type or "none",
        "study_type": study_type or "none",
    }

    current_run_payload = {
        "summary": current_summary,
        "manifest": {
            "run_id": run_id,
            "evidence_kind": evidence_kind,
            "model_mode": model_mode,
            "evaluator_type": evaluator_type or "none",
            "study_type": study_type or "none",
            "hashes": source_hashes,
        },
        "hashes": source_hashes,
        "evidence_kind": evidence_kind,
        "model_mode": model_mode,
    }

    previous_run = load_run_data(baseline_path) if baseline_path else None

    # Comparability & Metrics evaluation
    comparison = compare_runs(
        current_run=current_run_payload,
        baseline_run=previous_run or {},
    )

    eval_results = comparison["eval_results"]
    regressions = comparison["regressions_detected"]
    comparable = comparison["comparable"]
    incomp_reasons = comparison["incompatibility_reasons"]
    has_target_failure = comparison["has_target_failure"]

    # Manifest construction
    metric_prov_map = {}
    for r in eval_results:
        metric_prov_map[r["metric"]] = MetricProvenance(
            metric=r["metric"],
            value=r["current"],
            status=r["status"],
            evidence_ref=r["evidence_ref"],
            evidence_kind=evidence_kind,
            model_mode=model_mode,
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

    # Check mixed evidence
    manifest_check_data = {
        "evidence_kind": evidence_kind,
        "model_mode": model_mode,
        "profile": source_manifest.get("profile"),
        "metrics": metric_prov_map,
    }
    is_mixed, mixed_reasons = check_mixed_evidence(manifest_check_data)
    if is_mixed:
        has_target_failure = True
        print(f"\n[ERROR] Mixed evidence detected: {', '.join(mixed_reasons)}")

    # Enforce --require-live validation
    live_gate_errors: List[str] = []
    if require_live:
        if is_read_only or execution_mode == "cached_only":
            live_gate_errors.append("--require-live cannot be satisfied by read-only / cached execution.")
        if evidence_kind != "live":
            live_gate_errors.append(f"--require-live requires evidence_kind='live', got '{evidence_kind}'.")
        if model_mode != "trained":
            live_gate_errors.append(f"--require-live requires verified trained model_mode, got '{model_mode}'.")
        if is_mixed:
            live_gate_errors.append(f"Mixed evidence rejected: {', '.join(mixed_reasons)}")
        if is_synthetic:
            live_gate_errors.append(f"Synthetic benchmark rejected: {', '.join(audit_reasons)}")
        if has_target_failure:
            live_gate_errors.append("Target requirements not satisfied under live assertion.")
        if regressions:
            live_gate_errors.append("Regressions detected under live assertion.")

        if live_gate_errors:
            has_target_failure = True
            for err in live_gate_errors:
                print(f"[REQUIRE-LIVE FAILURE] {err}")

    all_mandatory_passed = (
        not has_target_failure
        and not regressions
        and not is_mixed
        and len(live_gate_errors) == 0
    )

    manifest = EvaluationManifest(
        run_id=run_id,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        git_commit=git_commit,
        evidence_kind=evidence_kind,
        model_mode=model_mode,
        evaluator_type=evaluator_type or "none",
        study_type=study_type or "none",
        execution_mode=execution_mode,
        hashes=source_hashes,
        config=cfg_data,
        counts={"total_evaluated_metrics": len(eval_results)},
        environment=env_data,
        metrics=metric_prov_map,
        files={
            source_snapshot_name: {
                "path": source_snapshot_name,
                "sha256": source_snapshot_sha256,
            }
        },
        all_mandatory_passed=all_mandatory_passed,
        summary_reason="All mandatory acceptance gates passed." if all_mandatory_passed else "Mandatory targets, comparability, or live requirements not satisfied.",
    )

    # 3. Output files into fresh run directory
    eval_json_path = run_dir / "evaluation_result.json"
    manifest_json_path = run_dir / "manifest.json"
    report_md_path = run_dir / "REGRESSION_REPORT.md"

    full_output = {
        "run_id": run_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_commit": git_commit,
        "execution_mode": execution_mode,
        "evidence_kind": evidence_kind,
        "model_mode": model_mode,
        "comparable_with_baseline": comparable,
        "incompatibility_reasons": incomp_reasons,
        "synthetic_audit_detected": is_synthetic,
        "audit_reasons": audit_reasons,
        "mixed_evidence_detected": is_mixed,
        "mixed_reasons": mixed_reasons,
        "live_gate_errors": live_gate_errors,
        "evaluation": eval_results,
        "regressions_detected": regressions,
        "all_mandatory_passed": all_mandatory_passed,
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
        f"> **Git Commit:** `{git_commit or 'untracked'}`  ",
        f"> **Evidence Kind:** `{evidence_kind}`  ",
        f"> **Execution Mode:** `{execution_mode}`  ",
        f"> **Model Mode:** `{model_mode}`  ",
        f"> **Evaluator Type:** `{evaluator_type or 'none'}`  ",
        f"> **Study Type:** `{study_type or 'none'}`  ",
        f"> **Regression Status:** `{'REGRESSION DETECTED' if regressions else 'NO REGRESSION (STABLE)'}`  ",
        f"> **Mandatory Gates Passed:** `{all_mandatory_passed}`  ",
        "",
    ]

    if execution_mode == "cached_only":
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

    if is_mixed:
        md_lines.extend([
            "> [!CAUTION]",
            f"> **Mixed Evidence Rejected:** {'; '.join(mixed_reasons)}.",
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

    audit_status_str = "FAIL (Synthetic detected)" if is_synthetic else ("UNVERIFIED (No signed model manifest)" if model_mode == "unverified" else "PASS (Verified)")
    md_lines.extend([
        "---",
        "",
        "## 3. Evaluation Provenance & Audit Summary",
        f"- **Run ID:** `{run_id}`",
        f"- **Run Directory:** `{run_dir}`",
        f"- **Manifest:** `{manifest_json_path}`",
        f"- **Source Snapshot:** `{source_snapshot_file}` (`{source_snapshot_sha256}`)",
        f"- **Synthetic Benchmark Audit:** `{audit_status_str}`",
        "",
    ])

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\nSaved evaluation artifacts to fresh directory:\n  {run_dir}")
    return run_dir, all_mandatory_passed


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

    run_dir, success = run_regression_evaluation(
        current_path=args.current,
        baseline_path=args.baseline,
        output_root=args.output_dir,
        cached_only=args.cached_only,
        skip_benchmark=args.skip_benchmark,
        require_live=args.require_live,
        evaluator_type=args.evaluator_type,
        study_type=args.study_type,
    )
    sys.exit(0 if success else 1)
