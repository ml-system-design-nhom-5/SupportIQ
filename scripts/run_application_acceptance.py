#!/usr/bin/env python3
"""CLI Acceptance Runner for SupportIQ Application & ML Evaluation (Task B3).

Usage:
    # Run application end-to-end acceptance in isolated schema (mock mode):
    python scripts/run_application_acceptance.py --mode mock

    # Run complete acceptance suite (E2E application + ML & baseline OOF audit):
    python scripts/run_application_acceptance.py --all

    # Run with verified pricing configuration:
    python scripts/run_application_acceptance.py --mode mock --pricing-file config/verified_pricing.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.application_acceptance import (
    ApplicationAcceptanceConfig,
    ApplicationAcceptanceRunner,
)
from pipeline.evaluation.ml_provenance_audit import run_ml_audit
from scripts.native_runtime import configure_runtime_environment


def parse_args():
    parser = argparse.ArgumentParser(
        description="SupportIQ Application Acceptance Runner (Task B3)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help="Evaluation mode: 'mock' (offline deterministic) or 'live' (requires running AI gateway)",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/evaluation/backend-evaluation",
        help="Output directory for reports and manifests (unique to backend-evaluation)",
    )
    parser.add_argument(
        "--secrets",
        default=None,
        help="Path to .local/application.json containing database credentials",
    )
    parser.add_argument(
        "--pricing-file",
        default=None,
        help="Path to verified pricing JSON with input_cost_per_million and output_cost_per_million",
    )
    parser.add_argument(
        "--num-warm",
        type=int,
        default=4,
        help="Number of warm ticket requests following initial cold start",
    )
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=25.0,
        help="Timeout in seconds for waiting on ticket suggestion completion",
    )
    parser.add_argument(
        "--run-ml-audit",
        action="store_true",
        help="Run ML & baseline OOF provenance and robustness audit",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run both application E2E acceptance runner and ML provenance audit",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    configure_runtime_environment()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    verified_pricing = None
    if args.pricing_file:
        p_path = Path(args.pricing_file)
        if p_path.exists():
            verified_pricing = json.loads(p_path.read_text(encoding="utf-8"))
        else:
            print(f"[WARN] Pricing file {p_path} not found; cost will be marked unavailable.")

    # 1. Run ML & baseline provenance audit if requested or --all
    if args.run_ml_audit or args.all:
        print("=== Running ML & Baseline OOF Provenance Audit ===")
        ml_res = run_ml_audit(REPO_ROOT, out_dir)
        print(f"ML Audit completed. DistilBERT OOF Macro-F1: {ml_res['distilbert_audit']['oof_macro_f1']:.4f}")
        print(f"Baseline Linear SVM OOF Macro-F1: {ml_res['baseline_audit']['candidates'][0]['oof_macro_f1']:.4f}")

    # 2. Run Application E2E Acceptance Runner
    print(f"\n=== Running Application End-to-End Acceptance Runner (mode={args.mode}) ===")
    config = ApplicationAcceptanceConfig(
        secrets_path=args.secrets,
        mode=args.mode,
        num_warm_requests=args.num_warm,
        poll_timeout_seconds=args.poll_timeout,
        verified_pricing=verified_pricing,
    )
    runner = ApplicationAcceptanceRunner(config)
    summary = runner.run(output_dir=out_dir)

    passed = summary["acceptance_summary"]["overall_passed"]
    p95 = summary["performance"]["p95_seconds"]
    oversight = summary["acceptance_summary"]["human_oversight_enforced"]
    cost_status = summary["tokens_and_cost"]["cost_status"]

    print(f"\nAcceptance Result: {'PASSED' if passed else 'FAILED'}")
    print(f"- End-to-End p95 Latency: {p95:.3f}s (target <= 12.0s: {'MET' if summary['performance']['target_p95_met'] else 'MISSED'})")
    print(f"- 100% Human Oversight (No Auto-Send): {'VERIFIED' if oversight else 'FAILED'}")
    print(f"- Token Usage: {summary['tokens_and_cost']['total_tokens']} total tokens")
    print(f"- Cost Status: {cost_status} (Cost USD: {summary['tokens_and_cost']['cost_usd']})")
    print(f"- Report written to: {out_dir / 'acceptance_e2e_report.md'}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
