"""Orchestration and execution runner for ML and System evaluation."""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from pipeline.preparation.utils import (
    CORE_PRODUCT_INTENTS,
    compute_sha256,
    get_next_id,
)
from pipeline.training.artifacts import (
    IntentModelBundle,
    write_json_atomic,
)
from pipeline.training.run_training import capture_environment
from pipeline.evaluation import EvaluationError
from pipeline.evaluation.benchmark import benchmark_classifier
from pipeline.evaluation.contracts import (
    _resolve_path,
    load_config,
    load_suite,
    validate_run_id,
    verify_ml_inputs,
)
from pipeline.evaluation.evaluate_intent import (
    classification_report_data,
    evaluate_robustness,
    get_score_capability,
    predict_rows,
)
from pipeline.evaluation.reporting import write_reports

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_ml_evaluation(
    training_manifest: str | Path,
    suite: str | Path | None,
    config_path: str | Path,
    run_id: str | None,
    repo_root: str | Path = REPO_ROOT,
    output_root: str | Path = "artifacts/evaluation",
) -> dict[str, Any]:
    """Execute evaluation on locked training models across hold-out test and robustness suite."""
    root = Path(repo_root)
    out_base = _resolve_path(str(output_root), root)

    if run_id is None:
        run_id = get_next_id(out_base)
    else:
        validate_run_id(run_id)

    run_dir = out_base / run_id
    if run_dir.exists():
        raise EvaluationError(f"Run directory already exists at {run_dir}")

    run_dir.mkdir(parents=True, exist_ok=False)
    state_file = run_dir / "run_state.json"
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write_json_atomic({"status": "running", "mode": "ml", "started_at": created_at}, state_file)

    try:
        resolved_cfg_path = _resolve_path(str(config_path), root)
        config = load_config(resolved_cfg_path)
        verified = verify_ml_inputs(training_manifest, root, config)

        suite_data: dict[str, Any] | None = None
        if suite:
            suite_data = load_suite(suite, root, mode="ml")

        initial_inputs = dict(verified.input_hashes)
        initial_inputs["config"] = compute_sha256(resolved_cfg_path)
        if suite_data:
            initial_inputs.update(suite_data["input_hashes"])

        # Write resolved config & environment
        write_json_atomic({"config": config, "mode": "ml"}, run_dir / "config.resolved.json")
        env = capture_environment(root)
        write_json_atomic(env, run_dir / "environment.json")

        models_results: dict[str, Any] = {}
        comp_rows: list[dict[str, Any]] = []

        selection_winner = verified.selection.get("winner", {})
        winner_cid = selection_winner.get("candidate_id")

        batch_size = config.get("timing", {}).get("throughput_batch_size", 256)

        for mid, mdir in verified.model_dirs.items():
            bundle = IntentModelBundle.load(mdir)
            preds_df = predict_rows(bundle, verified.test, batch_size=batch_size)
            eval_data = classification_report_data(
                preds_df,
                class_order=verified.class_order,
                core_intents=CORE_PRODUCT_INTENTS,
            )
            score_cap = get_score_capability(bundle)

            if suite_data:
                rob_data = evaluate_robustness(
                    bundle,
                    suite_data["robustness_cases"],
                    class_order=verified.class_order,
                )
            else:
                rob_data = {"cases_evaluated": 0, "slices": {}}

            bench_data = benchmark_classifier(
                bundle,
                verified.test["instruction"].tolist(),
                config,
            )

            metrics_payload = {
                **eval_data["metrics"],
                "score_capability": score_cap,
                "core_metrics": eval_data["core_metrics"],
            }

            models_results[mid] = {
                "predictions": preds_df,
                "metrics": metrics_payload,
                "per_class": eval_data["per_class"],
                "confusion_matrix": eval_data["confusion_matrix"],
                "robustness": rob_data,
                "latency": bench_data,
            }

            best_entry = verified.selection["best_per_model"].get(mid, {})
            cv_f1 = float(best_entry.get("macro_f1_mean", 0.0))
            is_winner = (best_entry.get("candidate_id") == winner_cid)

            comp_rows.append({
                "model_id": mid,
                "candidate_id": best_entry.get("candidate_id", mid),
                "cv_macro_f1": cv_f1,
                "test_macro_f1": eval_data["metrics"]["macro_f1"],
                "test_accuracy": eval_data["metrics"]["accuracy"],
                "test_weighted_f1": eval_data["metrics"]["weighted_f1"],
                "test_core_macro_f1": eval_data["core_metrics"]["macro_f1"],
                "latency_p50_ms": bench_data["latency"]["p50"] * 1000.0,
                "latency_p95_ms": bench_data["latency"]["p95"] * 1000.0,
                "throughput_items_sec": bench_data["throughput"]["items_per_second"],
                "is_cv_winner": is_winner,
            })

        comp_df = pd.DataFrame(comp_rows)
        winner_row = comp_df[comp_df["is_cv_winner"]].iloc[0] if not comp_df.empty else None

        results = {
            "models": models_results,
            "baseline_comparison": comp_df,
            "has_robustness_suite": bool(suite_data),
            "robustness_summary": f"Evaluated {suite_data['robustness_cases'].__len__()} cases" if suite_data else "No suite provided",
            "winner": {
                "candidate_id": winner_cid,
                "model_id": selection_winner.get("model_id"),
                "cv_macro_f1": float(selection_winner.get("macro_f1_mean", 0.0)),
                "test_macro_f1": float(winner_row["test_macro_f1"]) if winner_row is not None else 0.0,
            },
        }

        metadata = {
            "run_id": run_id,
            "mode": "ml",
            "timestamp": created_at,
            "training_run_id": verified.training_manifest.get("run_id"),
        }

        written_artifacts = write_reports(run_dir, results, metadata)

        all_input_paths = dict(verified.source_paths)
        all_input_paths["config"] = resolved_cfg_path
        if suite_data:
            all_input_paths.update(suite_data["source_paths"])

        # Check for mid-run input tampering across all data, config, and suite files
        for name, path in all_input_paths.items():
            current_hash = compute_sha256(path)
            if current_hash != initial_inputs[name]:
                raise EvaluationError(f"Input {name} changed during run")

        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json_atomic({"status": "completed", "completed_at": completed_at}, state_file)

        # Compute output hashes
        outputs: dict[str, str] = {}
        for file_path in sorted(run_dir.rglob("*")):
            if file_path.is_file() and file_path.name != "manifest.json":
                rel = file_path.relative_to(run_dir).as_posix()
                outputs[rel] = compute_sha256(file_path)

        manifest_data = {
            "schema_version": 1,
            "mode": "ml",
            "run_id": run_id,
            "status": "completed",
            "created_at": created_at,
            "completed_at": completed_at,
            "training_run_id": verified.training_manifest.get("run_id"),
            "inputs": initial_inputs,
            "outputs": outputs,
            "winner_locked": results["winner"],
        }
        write_json_atomic(manifest_data, run_dir / "manifest.json")

        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "manifest_path": str(run_dir / "manifest.json"),
            "results": results,
        }

    except Exception as exc:
        write_json_atomic(
            {"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}},
            state_file,
        )
        if isinstance(exc, EvaluationError):
            raise
        raise EvaluationError(f"Evaluation failed: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for running ML or System evaluation."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(description="Run Evaluation for SupportIQ ML models and system.")
    parser.add_argument("--mode", default="ml", choices=["ml"], help="Evaluation mode (ml)")
    parser.add_argument("--training-manifest", default=None, help="Path to completed training manifest.json")
    parser.add_argument("--suite", default=None, help="Path to robustness/system suite manifest")
    parser.add_argument("--config", required=True, help="Path to evaluation config JSON")
    parser.add_argument("--run-id", default=None, help="Optional run ID in DD-MM-YYYY-stt format")
    parser.add_argument("--output-root", default="artifacts/evaluation", help="Root dir for evaluation runs")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Root directory of the repository")

    args = parser.parse_args(argv)

    if not args.training_manifest:
        print("Error: --training-manifest is required when --mode=ml.", file=sys.stderr)
        return 1

    try:
        res = run_ml_evaluation(
            training_manifest=args.training_manifest,
            suite=args.suite,
            config_path=args.config,
            run_id=args.run_id,
            repo_root=REPO_ROOT,
            output_root=args.output_root,
        )
        print(f"=== Evaluation completed successfully! ===")
        print(f"Run dir: {res['run_dir']}")
        winner = res["results"]["winner"]
        print(f"CV Winner (Locked): {winner.get('candidate_id')} (CV Macro-F1: {winner.get('cv_macro_f1'):.4f})")
        print(f"Test Macro-F1: {winner.get('test_macro_f1'):.4f}")
        return 0
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
