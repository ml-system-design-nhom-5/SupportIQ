"""Reporting utilities, requirements matrix builder, and atomic report writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.training.artifacts import write_csv_atomic, write_json_atomic


def build_requirements_matrix(results: dict[str, Any], mode: str = "ml") -> pd.DataFrame:
    """Construct requirements compliance matrix differentiating ML and System evaluation gates."""
    winner_info = results.get("winner", {})
    winner_cid = winner_info.get("candidate_id", "unknown")
    cv_f1 = winner_info.get("cv_macro_f1", 0.0)
    test_f1 = winner_info.get("test_macro_f1", 0.0)

    cv_status = "pass" if cv_f1 >= 0.85 else "fail"
    robustness_eval = bool(results.get("has_robustness_suite"))

    matrix_rows = [
        {
            "requirement": "ML Quality (CV Macro-F1 >= 0.85)",
            "category": "ML",
            "evidence": f"CV Winner {winner_cid}: Macro-F1 = {cv_f1:.4f}",
            "status": cv_status,
            "notes": "10-fold cross-validation target from problem specification",
        },
        {
            "requirement": "ML Quality (Hold-out Test Macro-F1)",
            "category": "ML",
            "evidence": f"CV Winner {winner_cid}: Test Macro-F1 = {test_f1:.4f}",
            "status": "reported",
            "notes": "Locked hold-out test set evaluation; no post-test tuning permitted",
        },
        {
            "requirement": "ML Robustness (Perturbation Slices)",
            "category": "ML",
            "evidence": results.get("robustness_summary", "No suite provided"),
            "status": "reported" if robustness_eval else "not_evaluated",
            "notes": "Behavior under casing, typos, OOD, and entity variations",
        },
        {
            "requirement": "Retrieval Quality (Recall@3 >= 0.80)",
            "category": "System",
            "evidence": "N/A in ML evaluation mode",
            "status": "not_evaluated",
            "notes": "Evaluated during system retrieval pipeline benchmarking",
        },
        {
            "requirement": "LLM Grounding (>= 90% Supported Claims)",
            "category": "System",
            "evidence": "N/A in ML evaluation mode",
            "status": "not_evaluated",
            "notes": "Evaluated during system citation and claim annotation audit",
        },
        {
            "requirement": "Oversight & Safety (100% Escalation & Approval)",
            "category": "System",
            "evidence": "N/A in ML evaluation mode",
            "status": "not_evaluated",
            "notes": "Evaluated during system guardrail and policy verification",
        },
        {
            "requirement": "Reliability & Fault Tolerance",
            "category": "System",
            "evidence": "N/A in ML evaluation mode",
            "status": "not_evaluated",
            "notes": "Evaluated during system resilience and fallback testing",
        },
        {
            "requirement": "End-to-End Latency & Cost",
            "category": "System",
            "evidence": "N/A in ML evaluation mode",
            "status": "not_evaluated",
            "notes": "Classifier latency reported separately in baseline comparison",
        },
    ]

    return pd.DataFrame(matrix_rows)


def _df_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "*Empty table.*"
    headers = [str(c) for c in df.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in df.columns) + " |")
    return "\n".join(lines)


def _generate_markdown_report(results: dict[str, Any], metadata: dict[str, Any]) -> str:
    winner = results.get("winner", {})
    comp = results.get("baseline_comparison", pd.DataFrame())

    lines = [
        "# SupportIQ ML Evaluation Report",
        "",
        f"- **Run ID:** `{metadata.get('run_id')}`",
        f"- **Mode:** `{metadata.get('mode', 'ml')}`",
        f"- **Evaluation Date (UTC):** `{metadata.get('timestamp')}`",
        f"- **Training Run Ref:** `{metadata.get('training_run_id')}`",
        f"- **CV Winner (Locked):** `{winner.get('candidate_id')}` (CV Macro-F1: `{winner.get('cv_macro_f1', 0.0):.4f}`)",
        f"- **Test Macro-F1 (Winner):** `{winner.get('test_macro_f1', 0.0):.4f}`",
        "",
        "## 1. Baseline Model Comparison",
        "",
    ]
    if isinstance(comp, pd.DataFrame) and not comp.empty:
        lines.append(_df_to_markdown(comp))
    else:
        lines.append("*No comparison data available.*")

    lines.extend([
        "",
        "## 2. Invariants and Disclaimers",
        "",
        "- **Test Set Isolation:** The test set was held strictly blind during feature extraction, training, and CV selection.",
        "- **Winner Immutability:** The CV-selected winner is fixed; test set rankings cannot override the CV winner.",
        "- **Data Limitations:** Evaluated on the Bitext Retail & E-Commerce dataset. Real customer traffic may exhibit out-of-scope intent drift, complex multi-intent statements, and domain shifts.",
        "- **Scope Disclaimer:** This evaluation covers ML intent classification baselines only. System-level gates (retrieval, grounding, policy guardrails) remain marked as `not_evaluated` until system benchmarking.",
        "",
    ])
    return "\n".join(lines)


def write_reports(
    run_dir: Path,
    results: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Path]:
    """Write all model reports, comparison matrices, and summary markdown atomically."""
    written: dict[str, Path] = {}

    intent_base = run_dir / "intent"
    for mid, mdata in results.get("models", {}).items():
        mdir = intent_base / mid
        mdir.mkdir(parents=True, exist_ok=True)

        if "predictions" in mdata and isinstance(mdata["predictions"], pd.DataFrame):
            written[f"intent/{mid}/predictions.csv"] = write_csv_atomic(
                mdata["predictions"], mdir / "predictions.csv", index=False
            )
        if "metrics" in mdata:
            written[f"intent/{mid}/metrics.json"] = write_json_atomic(
                mdata["metrics"], mdir / "metrics.json"
            )
        if "per_class" in mdata and isinstance(mdata["per_class"], pd.DataFrame):
            written[f"intent/{mid}/per_class.csv"] = write_csv_atomic(
                mdata["per_class"], mdir / "per_class.csv", index=True
            )
        if "confusion_matrix" in mdata and isinstance(mdata["confusion_matrix"], pd.DataFrame):
            written[f"intent/{mid}/confusion_matrix.csv"] = write_csv_atomic(
                mdata["confusion_matrix"], mdir / "confusion_matrix.csv", index=True
            )
        if "robustness" in mdata:
            rob_df = pd.DataFrame(mdata["robustness"].get("slices", {}).values())
            written[f"intent/{mid}/robustness.csv"] = write_csv_atomic(
                rob_df, mdir / "robustness.csv", index=False
            )
        if "latency" in mdata:
            written[f"intent/{mid}/latency.json"] = write_json_atomic(
                mdata["latency"], mdir / "latency.json"
            )

    comp_df = results.get("baseline_comparison")
    if isinstance(comp_df, pd.DataFrame):
        written["baseline_comparison.csv"] = write_csv_atomic(
            comp_df, run_dir / "baseline_comparison.csv", index=False
        )

    req_df = build_requirements_matrix(results, mode=metadata.get("mode", "ml"))
    written["requirements_matrix.csv"] = write_csv_atomic(
        req_df, run_dir / "requirements_matrix.csv", index=False
    )

    md_content = _generate_markdown_report(results, metadata)
    md_path = run_dir / "report.md"
    md_tmp = run_dir / ".report.md.tmp"
    md_tmp.write_text(md_content, encoding="utf-8")
    import os
    os.replace(md_tmp, md_path)
    written["report.md"] = md_path

    return written
