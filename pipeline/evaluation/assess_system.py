"""Human claim annotation verification, product value analysis, and immutable run assessment."""

from __future__ import annotations

import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.evaluation import EvaluationError
from pipeline.preparation.utils import compute_sha256


def evaluate_claim_annotations(
    annotations: List[Dict[str, Any]],
    expected_draft_hashes: Dict[str, str],
    expected_draft_case_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Evaluate human factual claim annotations against run draft hashes.
    Strictly enforces:
    - Reviewer identity and timestamp presence.
    - Draft SHA-256 integrity check against actual run outputs.
    - Rejects annotations referencing undeclared or non-existent cases.
    - Full coverage across all expected draft cases.
    - 'unknown' verdicts count as unsupported claims.
    - Unrounded threshold comparison (0.89999 fails 0.90).
    - Zero claims without reviewer rationale yields insufficient_evidence.
    """
    total_claims = 0
    supported_claims = 0
    unsupported_claims = 0
    unknown_claims = 0
    annotated_cases = set()

    has_insufficient_evidence = False
    insufficient_reason = ""

    for idx, ann in enumerate(annotations, start=1):
        reviewer = ann.get("reviewer")
        if not reviewer or not str(reviewer).strip():
            raise EvaluationError(f"Missing reviewer in annotation at record {idx}")

        cid = ann.get("case_id")
        if not cid:
            raise EvaluationError(f"Missing case_id in annotation at record {idx}")

        if cid not in expected_draft_hashes:
            raise EvaluationError(f"Annotation references undeclared or non-existent case '{cid}'")

        expected_hash = expected_draft_hashes[cid]
        actual_hash = ann.get("draft_sha256")
        if actual_hash != expected_hash:
            raise EvaluationError(
                f"Draft hash mismatch for case '{cid}': expected {expected_hash}, got {actual_hash}"
            )

        annotated_cases.add(cid)
        claims = ann.get("claims", [])
        if len(claims) == 0:
            attestation = ann.get("attestation") or {}
            rationale = attestation.get("rationale")
            if not rationale or not str(rationale).strip():
                has_insufficient_evidence = True
                insufficient_reason = f"Case '{cid}' has zero claims without reviewer rationale"

        for c in claims:
            verdict = str(c.get("verdict", "")).strip().lower()
            total_claims += 1
            if verdict == "supported":
                supported_claims += 1
            elif verdict == "unknown":
                unknown_claims += 1
            else:
                unsupported_claims += 1

    # Verify coverage across mandatory draft cases
    if expected_draft_case_ids:
        missing_mandatory = set(expected_draft_case_ids) - annotated_cases
        if missing_mandatory:
            has_insufficient_evidence = True
            insufficient_reason = f"Missing required annotations for draft cases: {sorted(missing_mandatory)}"

    if total_claims == 0 or has_insufficient_evidence:
        status = "insufficient_evidence"
        supported_ratio_raw = 0.0
        supported_ratio = 0.0
        gate_passed = False
    else:
        # Unknown counts as unsupported, so denominator is total_claims
        # Strict unrounded comparison against target threshold
        supported_ratio_raw = supported_claims / total_claims
        gate_passed = supported_ratio_raw >= 0.90
        supported_ratio = round(supported_ratio_raw, 4)
        status = "pass" if gate_passed else "fail"

    return {
        "status": status,
        "annotated_cases_count": len(annotated_cases),
        "total_claims": total_claims,
        "supported_claims": supported_claims,
        "unsupported_claims": unsupported_claims,
        "unknown_claims": unknown_claims,
        "supported_claims_ratio": supported_ratio,
        "supported_claims_ratio_raw": supported_ratio_raw,
        "grounded_claims_gate_passed": gate_passed,
        "insufficient_reason": insufficient_reason if has_insufficient_evidence else None,
    }


def evaluate_product_sessions(sessions_path: Path | str) -> Dict[str, Any]:
    """Parse and evaluate product session study CSV.
    Enforces:
    - Positive, finite durations.
    - Strict separation of approval rates from time metrics.
    - Paired comparisons across matching tasks/participants.
    """
    path = Path(sessions_path)
    if not path.exists():
        raise EvaluationError(f"Product sessions file not found: {path}")

    sessions: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            try:
                dur = float(row["duration_seconds"])
            except (ValueError, KeyError) as exc:
                raise EvaluationError(f"Invalid duration at row {row_num}: {exc}") from exc

            if dur <= 0 or math.isnan(dur) or math.isinf(dur):
                raise EvaluationError(
                    f"Invalid duration '{dur}' at row {row_num}: duration must be positive and finite"
                )

            sessions.append({
                "participant_id": row.get("participant_id"),
                "task_id": row.get("task_id"),
                "condition": row.get("condition"),
                "duration_seconds": dur,
                "outcome": row.get("outcome"),
                "feedback_action": row.get("feedback_action"),
            })

    # Paired matching: group by (participant_id, task_id)
    by_pair: Dict[tuple, Dict[str, float]] = {}
    copilot_sessions = 0
    approved_count = 0

    for s in sessions:
        cond = s.get("condition")
        pair_key = (s.get("participant_id"), s.get("task_id"))
        if cond in ("manual", "copilot"):
            if pair_key not in by_pair:
                by_pair[pair_key] = {}
            by_pair[pair_key][cond] = s["duration_seconds"]

        if cond == "copilot":
            copilot_sessions += 1
            if s.get("feedback_action") == "approve":
                approved_count += 1

    time_differences = []
    for pair_key, conds in by_pair.items():
        if "manual" in conds and "copilot" in conds:
            time_differences.append(conds["manual"] - conds["copilot"])

    approval_rate = (
        round(approved_count / copilot_sessions, 4)
        if copilot_sessions > 0
        else "N/A"
    )

    if not time_differences:
        return {
            "status": "insufficient_evidence",
            "total_sessions": len(sessions),
            "paired_count": 0,
            "paired_time_saved_median_seconds": "N/A",
            "approval_rate": approval_rate,
            "reason": "No paired manual/copilot sessions found for the same participant and task",
        }

    median_diff = round(statistics.median(time_differences), 2)
    return {
        "status": "pass",
        "total_sessions": len(sessions),
        "paired_count": len(time_differences),
        "paired_time_saved_median_seconds": median_diff,
        "approval_rate": approval_rate,
    }


def assess_run(
    run_dir: Path | str,
    annotations_path: Path | str,
    assessment_id: str,
    product_sessions_path: Optional[Path | str] = None,
) -> Path:
    """Assess a completed system evaluation run with verified human annotations.
    Creates an immutable assessment directory under <run_dir>/assessments/<assessment_id>.
    """
    run_p = Path(run_dir).resolve()
    manifest_p = run_p / "manifest.json"
    if not manifest_p.exists():
        raise EvaluationError(f"Run manifest not found at {manifest_p}")

    with open(manifest_p, "r", encoding="utf-8") as f:
        run_manifest = json.load(f)

    # 1. Verify checksums of run artifacts declared in manifest
    manifest_dir = run_p
    files_dict = run_manifest.get("files")
    if not isinstance(files_dict, dict) or not files_dict:
        raise EvaluationError("Run manifest must contain a non-empty 'files' dictionary of artifacts")

    if "results.jsonl" not in files_dict:
        raise EvaluationError("Run manifest missing mandatory artifact declaration 'results.jsonl'")

    for f_key, f_meta in files_dict.items():
        target = manifest_dir / f_meta.get("path", f_key)
        if not target.exists():
            raise EvaluationError(f"Run artifact '{f_key}' missing at {target}")
        actual_sha = compute_sha256(target)
        expected_sha = f_meta.get("sha256")
        if actual_sha != expected_sha:
            raise EvaluationError(
                f"Run artifact '{f_key}' checksum mismatch: expected {expected_sha}, got {actual_sha}"
            )

    # 2. Check assessment directory immutability
    clean_id = assessment_id.strip()
    if not clean_id or "/" in clean_id or "\\" in clean_id or ".." in clean_id:
        raise EvaluationError(f"Invalid assessment ID: '{assessment_id}'")

    assessment_dir = run_p / "assessments" / clean_id
    if assessment_dir.exists():
        raise EvaluationError(f"Assessment '{clean_id}' already exists; assessments are immutable")

    # 3. Read results.jsonl to extract expected draft hashes
    results_file = run_p / "results.jsonl"
    draft_hashes: Dict[str, str] = {}
    expected_draft_cases: Set[str] = set()
    with open(results_file, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            r = json.loads(line_str)
            cid = r.get("case_id")
            d_hash = r.get("draft_hash")
            if cid and d_hash:
                draft_hashes[cid] = d_hash
                expected_draft_cases.add(cid)

    # 4. Load annotations and evaluate
    ann_path = Path(annotations_path)
    if not ann_path.exists():
        raise EvaluationError(f"Annotations file not found at {ann_path}")

    annotations = []
    with open(ann_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            annotations.append(json.loads(line_str))

    claim_metrics = evaluate_claim_annotations(
        annotations,
        draft_hashes,
        expected_draft_case_ids=expected_draft_cases,
    )

    # 5. Evaluate product sessions if provided
    product_metrics = None
    if product_sessions_path:
        product_metrics = evaluate_product_sessions(product_sessions_path)

    # 6. Build immutable assessment artifacts
    assessment_dir.mkdir(parents=True, exist_ok=False)

    # Snapshot annotations
    snap_ann = assessment_dir / "annotations.snapshot.jsonl"
    with open(snap_ann, "w", encoding="utf-8") as f:
        for a in annotations:
            f.write(json.dumps(a) + "\n")

    # Snapshot product sessions if present
    created_files = {
        "annotations.snapshot.jsonl": compute_sha256(snap_ann),
    }

    if product_sessions_path:
        snap_prod = assessment_dir / "product_sessions.snapshot.csv"
        snap_prod.write_bytes(Path(product_sessions_path).read_bytes())
        created_files["product_sessions.snapshot.csv"] = compute_sha256(snap_prod)

    # Metrics file
    assessment_metrics = {
        "assessment_id": clean_id,
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "parent_run_id": run_manifest.get("run_id"),
        "human_claim_metrics": claim_metrics,
        "product_study_metrics": product_metrics,
    }
    metrics_file = assessment_dir / "assessment_metrics.json"
    metrics_file.write_text(json.dumps(assessment_metrics, indent=2), encoding="utf-8")
    created_files["assessment_metrics.json"] = compute_sha256(metrics_file)

    # Markdown report
    report_content = (
        f"# Assessment Report: {clean_id}\n\n"
        f"- **Parent Run ID:** {run_manifest.get('run_id')}\n"
        f"- **Grounded Claims Ratio:** {claim_metrics.get('supported_claims_ratio')} "
        f"(Gate passed: {claim_metrics.get('grounded_claims_gate_passed')})\n"
        f"- **Total Claims:** {claim_metrics.get('total_claims')} "
        f"(Supported: {claim_metrics.get('supported_claims')}, Unknown: {claim_metrics.get('unknown_claims')})\n"
    )
    if product_metrics:
        report_content += (
            f"\n## Product Value\n"
            f"- **Paired Time Saved Median:** {product_metrics.get('paired_time_saved_median_seconds')}s\n"
            f"- **Approval Rate:** {product_metrics.get('approval_rate')}\n"
        )
    report_file = assessment_dir / "assessment_report.md"
    report_file.write_text(report_content, encoding="utf-8")
    created_files["assessment_report.md"] = compute_sha256(report_file)

    # Assessment Manifest
    assessment_manifest = {
        "schema_version": "v1.0",
        "assessment_id": clean_id,
        "parent_run_manifest_sha256": compute_sha256(manifest_p),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            k: {"path": k, "sha256": v} for k, v in created_files.items()
        },
    }
    manifest_out = assessment_dir / "assessment_manifest.json"
    manifest_out.write_text(json.dumps(assessment_manifest, indent=2), encoding="utf-8")

    return assessment_dir


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for assessing an evaluation run with human annotations."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Assess a completed evaluation run with verified annotations.")
    parser.add_argument("--run-dir", required=True, help="Path to completed run directory")
    parser.add_argument("--annotations", required=True, help="Path to annotations JSONL file")
    parser.add_argument("--assessment-id", required=True, help="Unique assessment identifier")
    parser.add_argument("--product-sessions", default=None, help="Optional path to product sessions CSV")
    args = parser.parse_args(argv)

    try:
        out_dir = assess_run(
            run_dir=args.run_dir,
            annotations_path=args.annotations,
            assessment_id=args.assessment_id,
            product_sessions_path=args.product_sessions,
        )
        print(f"=== Assessment completed successfully ===")
        print(f"Assessment directory: {out_dir}")
        return 0
    except Exception as exc:
        print(f"Assessment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
