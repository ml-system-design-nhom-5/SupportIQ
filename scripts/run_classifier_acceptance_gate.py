#!/usr/bin/env python3
"""Run Task C independent classifier acceptance gate against serving vs candidate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.classifier_acceptance_gate import run_classifier_acceptance_gate


def _render_md(report: dict) -> str:
    srv = report["serving_baseline_evaluation"]
    cand = report["candidate_evaluation"]
    lines = [
        "# Task C Independent Classifier Acceptance Gate Report",
        "",
        f"- **Generated At:** `{report['generated_at']}`",
        f"- **Gate Decision:** **`{report['gate_decision']}`**",
        f"- **Failure Reasons:** `{report['failure_reasons']}`",
        f"- **Suite Boundary Note:** {report['suite_classification_note']}",
        "",
        "## 1. Provenance & Split Isolation",
        "",
        f"- **Candidate Dir:** `{report['provenance_audit']['candidate_dir']}`",
        f"- **Valid 46-Label Bijection:** `{report['provenance_audit']['valid_46_label_bijection']}`",
        f"- **Provenance Passed:** `{report['provenance_audit']['provenance_passed']}` (`{report['provenance_audit']['failure_reasons']}`)",
        f"- **Split Isolation & Gold Contamination Passed:** `{report['split_isolation_and_contamination']['passed']}` (`{report['split_isolation_and_contamination']['failure_reasons']}`)",
        "",
    ]
    if cand:
        sreg = srv["known_acceptance_regression_not_unseen_holdout"]
        creg = cand["known_acceptance_regression_not_unseen_holdout"]
        lines.extend(
            [
                "## 2. Serving vs Candidate Comparison",
                "",
                "| Suite / Check | Serving (`distilbert-supportiq`) | Candidate | Notes |",
                "| :--- | :--- | :--- | :--- |",
                f"| **ML OOD (N=80) Leaks** | `{srv['ml_oos_80']['false_draft_eligible_count']}/80` | `{cand['ml_oos_80']['false_draft_eligible_count']}/80` (`{cand['ml_oos_80']['false_draft_case_ids']}`) | Zero OOD leaks required |",
                f"| **ML Noise (N=420) 12-Label Acc / Macro-F1** | `{srv['ml_noise_420']['accuracy_12']:.4f}` / `{srv['ml_noise_420']['macro_f1_12']:.4f}` | `{cand['ml_noise_420']['accuracy_12']:.4f}` / `{cand['ml_noise_420']['macro_f1_12']:.4f}` | 12 supported labels in `ml_noise` |",
                f"| **System Acceptance 34-Label (N=39) Acc / Macro-F1** | `{sreg['system_acceptance_156']['escalated_34_accuracy']:.4f}` / `{sreg['system_acceptance_156']['escalated_34_macro_f1']:.4f}` | `{creg['system_acceptance_156']['escalated_34_accuracy']:.4f}` / `{creg['system_acceptance_156']['escalated_34_macro_f1']:.4f}` | All 34 escalated labels (`system_acceptance`) |",
                f"| **ML Noise ECE / Binary Brier** | `{srv['ml_noise_420']['ece_10bin']:.4f}` / `{srv['ml_noise_420']['binary_top_label_brier']:.4f}` | `{cand['ml_noise_420']['ece_10bin']:.4f}` / `{cand['ml_noise_420']['binary_top_label_brier']:.4f}` | Top-1 binary Brier |",
                f"| **Known Acceptance Regression (`system_acceptance` 34 `draft_expected`) Raw / Correct-Intent** | `{sreg['system_acceptance_156']['draft_expected_34_raw_draft']}/34` / `{sreg['system_acceptance_156']['draft_expected_34_correct_intent_draft']}/34` | `{creg['system_acceptance_156']['draft_expected_34_raw_draft']}/34` / `{creg['system_acceptance_156']['draft_expected_34_correct_intent_draft']}/34` | Regression suite, NOT unseen holdout |",
                f"| **Known Acceptance Regression (`system_acceptance` 63 Mandatory) Strict Match / Real Leaks** | `{sreg['system_acceptance_156']['mandatory_63_strict_match']}/63` / `{sreg['system_acceptance_156']['mandatory_63_real_unsafe_draft_leaks']}` | `{creg['system_acceptance_156']['mandatory_63_strict_match']}/63` / `{creg['system_acceptance_156']['mandatory_63_real_unsafe_draft_leaks']}` | Strict `expected.actions` match |",
                f"| **Known Acceptance Regression (`final_acceptance` 12 Answerable) Raw / Correct-Intent / Wrong-Intent IDs** | `{sreg['final_acceptance_24']['answerable_12_raw_draft']}/12` / `{sreg['final_acceptance_24']['answerable_12_correct_intent_draft']}/12` (`{sreg['final_acceptance_24']['answerable_12_wrong_intent_draft_cases']}`) | `{creg['final_acceptance_24']['answerable_12_raw_draft']}/12` / `{creg['final_acceptance_24']['answerable_12_correct_intent_draft']}/12` (`{creg['final_acceptance_24']['answerable_12_wrong_intent_draft_cases']}`) | Regression suite, NOT unseen holdout |",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Task C candidate classifier acceptance gate.")
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument(
        "--serving-dir",
        type=Path,
        default=REPO_ROOT / "artifacts/models/trained/distilbert-supportiq",
    )
    parser.add_argument("--candidate-manifest", type=Path, default=None)
    parser.add_argument("--train-split", type=Path, default=None)
    parser.add_argument("--calibration-split", type=Path, default=None)
    parser.add_argument("--eval-split", type=Path, default=None)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "artifacts/evaluation/classifier_gate_20261113",
    )
    args = parser.parse_args()

    out_dir = args.out_dir if args.out_dir.is_absolute() else (REPO_ROOT / args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = run_classifier_acceptance_gate(
        repo_root=REPO_ROOT,
        candidate_name=args.candidate_name,
        candidate_dir=args.candidate_dir,
        serving_dir=args.serving_dir,
        candidate_manifest_path=args.candidate_manifest,
        train_split_path=args.train_split,
        calibration_split_path=args.calibration_split,
        eval_split_path=args.eval_split,
    )
    (out_dir / "gate_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "CLASSIFIER_GATE_REPORT.md").write_text(_render_md(report), encoding="utf-8")
    print(f"Gate decision for {args.candidate_name}: {report['gate_decision']} | reasons={report['failure_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
