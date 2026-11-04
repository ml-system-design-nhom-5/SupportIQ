"""Comparison runner benchmarking baseline models and transformer classifiers."""

from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.benchmark import benchmark_classifier, scoped_num_threads
from pipeline.evaluation.comparison_contracts import (
    BASELINE_MODELS,
    TRANSFORMER_MODELS,
    load_comparison_config,
    verify_comparison_inputs,
)
from pipeline.evaluation.contracts import _resolve_path, validate_run_id
from pipeline.evaluation.evaluate_intent import (
    classification_report_data,
    predict_rows,
)
from pipeline.evaluation.reporting import _df_to_markdown
from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter
from pipeline.preparation.utils import (
    CORE_PRODUCT_INTENTS,
    compute_sha256,
    get_next_id,
)
from pipeline.training.artifacts import (
    IntentModelBundle,
    write_csv_atomic,
    write_json_atomic,
)
from pipeline.training.run_training import capture_environment

REPO_ROOT = Path(__file__).resolve().parents[2]


def _generate_comparison_markdown_report(
    comp_df: pd.DataFrame,
    model_registry: dict[str, Any],
    metadata: dict[str, Any],
    cuda_df: pd.DataFrame | None = None,
) -> str:
    """Generate comprehensive comparison markdown report distinguishing independent hold-out vs descriptive."""
    winner_cid = metadata.get("winner_candidate_id", "linear_svm__v1")
    winner_mid = metadata.get("winner_model_id", "linear_svm")

    independent_rows = comp_df[comp_df["eligible_for_independent_ranking"] == True]
    descriptive_rows = comp_df[comp_df["eligible_for_independent_ranking"] == False]

    lines = [
        "# SupportIQ Classifier Comparison Report: Transformers vs Baselines",
        "",
        f"- **Run ID:** `{metadata.get('run_id')}`",
        f"- **Mode:** `{metadata.get('mode', 'comparison')}`",
        f"- **Evaluation Date (UTC):** `{metadata.get('timestamp')}`",
        f"- **CPU Threads (Locked):** `{metadata.get('num_threads', 1)}`",
        f"- **CV Winner (Locked):** `{winner_cid}` (Model: `{winner_mid}`)",
        "",
        "## 1. Independent Hold-out Benchmark (Hold-out có bằng chứng độc lập)",
        "",
        "Models in this section possess verified training split provenance demonstrating strict blind isolation from the SupportIQ test set.",
        "",
    ]

    if not independent_rows.empty:
        lines.append(_df_to_markdown(independent_rows[[
            "model_id", "candidate_id", "is_cv_winner", "cv_macro_f1", "test_macro_f1",
            "test_accuracy", "test_core_macro_f1", "latency_p50_ms", "latency_p95_ms", "throughput_items_sec"
        ]]))
    else:
        lines.append("*No models with verified independent provenance.*")

    lines.extend([
        "",
        "## 2. Descriptive Results / Unverified Overlap Risk (Kết quả mô tả / Nguy cơ trùng dữ liệu)",
        "",
        "> [!WARNING]",
        "> **Unverified Training Split Overlap Risk:** The models below lack sample membership evidence proving hold-out independence from the Bitext test set. Their scores are purely descriptive and **must NOT be ranked or declared superior to independent baseline hold-out metrics**.",
        "",
    ])

    if not descriptive_rows.empty:
        lines.append(_df_to_markdown(descriptive_rows[[
            "model_id", "origin", "independence_status", "test_macro_f1", "test_accuracy",
            "test_core_macro_f1", "latency_p50_ms", "latency_p95_ms", "throughput_items_sec", "training_samples"
        ]]))
    else:
        lines.append("*None.*")

    lines.extend([
        "",
        "## 3. Complete 5-Model Comparison Matrix (CPU)",
        "",
    ])
    lines.append(_df_to_markdown(comp_df))

    if cuda_df is not None and not cuda_df.empty:
        lines.extend([
            "",
            "## 4. CUDA Acceleration Profile (GPU Supplementary Benchmark)",
            "",
            "Transformer latency measured on NVIDIA CUDA GPU with hardware synchronization:",
            "",
            _df_to_markdown(cuda_df),
        ])

    has_tf_cv = any(
        r.get("cv_protocol") == "10-fold cross-validation"
        for r in comp_df[comp_df["model_type"] == "transformer"].to_dict("records")
    )
    if has_tf_cv:
        budget_note = (
            "- **Training Budget Parity:** Both baseline models and local Transformer (`supportiq_distilbert`) "
            "were evaluated using 10-fold CV on the full 37,911 development samples, establishing fair and directly comparable benchmarks."
        )
    else:
        budget_note = (
            "- **Training Budget Disparity:** Baseline models were trained on 37,911 samples with 10-fold CV. "
            "The local Transformer was fine-tuned on a 9,200 sample subset with 1,840 validation split (no 10-fold CV). "
            "Raw score differences must not be conflated with algorithmic superiority."
        )

    lines.extend([
        "",
        "## 5. Invariants and Governance Rules",
        "",
        "- **Winner Immutability:** The cross-validation winner (`linear_svm`) is permanently locked from 10-fold CV. Test set rankings do NOT override the CV selection.",
        budget_note,
        "- **Hardware Latency Parity:** All 5 models in the primary comparison matrix were benchmarked on the identical sequential CPU inference protocol (batch=1, locked thread count, tokenizer included, weights pre-loaded).",
        "",
    ])

    return "\n".join(lines)


def run_comparison(
    config_path: str | Path,
    run_id: str | None,
    repo_root: str | Path = REPO_ROOT,
    output_root: str | Path = Path("artifacts/evaluation"),
) -> dict[str, Any]:
    """Execute 5-model comparison benchmarking 3 baselines and 2 transformers."""
    root = Path(repo_root).resolve()
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
    write_json_atomic({"status": "running", "mode": "comparison", "started_at": created_at}, state_file)

    try:
        resolved_cfg_path = _resolve_path(str(config_path), root)
        config = load_comparison_config(resolved_cfg_path, repo_root=root)
        verified = verify_comparison_inputs(config, repo_root=root)

        test_df = verified["test"]
        class_order = verified["class_order"]
        baseline_model_dirs = verified["baseline_model_dirs"]
        baseline_selection = verified.get("baseline_selection", {})
        transformer_specs = verified["transformer_specs"]
        historical_results = verified["historical_results"]
        source_paths = dict(verified["source_paths"])
        initial_inputs = dict(verified["input_hashes"])
        initial_inputs["config"] = compute_sha256(resolved_cfg_path)
        source_paths["config"] = resolved_cfg_path

        # Write resolved config & environment
        write_json_atomic({"config": config, "mode": "comparison"}, run_dir / "config.resolved.json")
        env = capture_environment(root)
        for extra_lib in ("torch", "transformers", "tokenizers", "safetensors"):
            try:
                env.setdefault("libraries", {})[extra_lib] = importlib.metadata.version(extra_lib)
            except Exception:
                env.setdefault("libraries", {})[extra_lib] = "not_installed"
        write_json_atomic(env, run_dir / "environment.json")

        num_threads = config.get("num_threads", 1)
        device = config.get("device", "cpu")
        batch_size = config.get("timing", {}).get("throughput_batch_size", 256)

        hist_winner = historical_results.get("winner_locked", {})
        winner_cid = hist_winner.get("candidate_id") or baseline_selection.get("winner", {}).get("candidate_id", "linear_svm__v1")
        winner_mid = hist_winner.get("model_id") or baseline_selection.get("winner", {}).get("model_id", "linear_svm")

        models_results: dict[str, Any] = {}
        comp_rows: list[dict[str, Any]] = []
        model_registry: dict[str, Any] = {}

        # 1. Baseline models: import predictions, recompute metrics, remeasure latency
        for mid in sorted(BASELINE_MODELS):
            mdir = baseline_model_dirs[mid]
            hist_entry = historical_results["models"][mid]
            preds_df = hist_entry["predictions_df"]
            hist_metrics = hist_entry.get("metrics", {})

            eval_data = classification_report_data(
                preds_df,
                class_order=class_order,
                core_intents=CORE_PRODUCT_INTENTS,
            )

            # Check numeric tolerance against historical metrics if present
            if "macro_f1" in hist_metrics:
                diff = abs(eval_data["metrics"]["macro_f1"] - float(hist_metrics["macro_f1"]))
                if diff > 1e-9:
                    raise EvaluationError(
                        f"Recomputed macro_f1 differs from historical by {diff:.10f} for {mid}"
                    )

            # Load baseline bundle strictly to remeasure latency under current hardware settings (strictly CPU)
            bundle = IntentModelBundle.load(mdir)
            with scoped_num_threads(num_threads):
                bench_data = benchmark_classifier(
                    bundle,
                    test_df["instruction"].tolist(),
                    dict(config, device="cpu"),
                )

            best_entry = baseline_selection.get("best_per_model", {}).get(mid, {})
            cv_f1 = float(best_entry.get("macro_f1_mean", 0.0))
            is_winner = (mid == winner_mid)

            models_results[mid] = {
                "predictions": preds_df,
                "metrics": {
                    **eval_data["metrics"],
                    "core_metrics": eval_data["core_metrics"],
                    "source_mode": {
                        "predictions": "imported_and_verified",
                        "metrics": "recomputed_from_verified_predictions",
                        "latency": "remeasured",
                    },
                },
                "per_class": eval_data["per_class"],
                "confusion_matrix": eval_data["confusion_matrix"],
                "latency": bench_data,
            }

            comp_rows.append({
                "model_id": mid,
                "candidate_id": best_entry.get("candidate_id", mid),
                "model_type": "baseline",
                "origin": "local_baseline_training",
                "independence_status": "verified",
                "eligible_for_independent_ranking": True,
                "is_cv_winner": is_winner,
                "cv_macro_f1": cv_f1,
                "test_macro_f1": eval_data["metrics"]["macro_f1"],
                "test_accuracy": eval_data["metrics"]["accuracy"],
                "test_weighted_f1": eval_data["metrics"]["weighted_f1"],
                "test_core_macro_f1": eval_data["core_metrics"]["macro_f1"],
                "latency_p50_ms": bench_data["latency"]["p50"] * 1000.0,
                "latency_p95_ms": bench_data["latency"]["p95"] * 1000.0,
                "throughput_items_sec": bench_data["throughput"]["items_per_second"],
                "training_samples": 37911,
                "cv_protocol": "10-fold cross-validation",
            })

            bundle_path = mdir / "bundle.joblib"
            model_registry[mid] = {
                "model_id": mid,
                "candidate_id": best_entry.get("candidate_id", mid),
                "type": "baseline",
                "origin": "local_baseline_training",
                "provenance_status": "verified",
                "eligible_for_independent_ranking": True,
                "preprocessing": "TF-IDF (unigram + bigram, max_features=10000, sublinear_tf=True)",
                "device": "cpu",
                "training_samples": 37911,
                "cv_protocol": "10-fold cross-validation",
                "artifact_hashes": {
                    "bundle": compute_sha256(bundle_path) if bundle_path.exists() else "unknown"
                },
            }

        # 2. Transformer models: predict on holdout, compute metrics, measure latency
        cuda_rows: list[dict[str, Any]] = []
        is_cuda_requested = (device == "cuda")
        if is_cuda_requested:
            import torch

            if not torch.cuda.is_available():
                raise EvaluationError("CUDA device requested but torch.cuda.is_available() is False")

        for mid in sorted(TRANSFORMER_MODELS):
            spec = transformer_specs[mid]
            adapter = TransformerIntentAdapter(
                model_dir=spec["model_dir"],
                model_id=mid,
                max_length=config.get("max_length", 64),
                device="cpu",
            )

            # Taxonomy verification: adapter classes must match verified class_order
            if set(adapter.classes_) != set(class_order):
                missing = sorted(set(class_order) - set(adapter.classes_))
                extra = sorted(set(adapter.classes_) - set(class_order))
                raise EvaluationError(
                    f"Model {mid} taxonomy mismatch against verified class_order: missing {missing}, extra {extra}"
                )

            preds_df = predict_rows(adapter, test_df, batch_size=batch_size)
            eval_data = classification_report_data(
                preds_df,
                class_order=class_order,
                core_intents=CORE_PRODUCT_INTENTS,
            )

            with scoped_num_threads(num_threads):
                bench_data = benchmark_classifier(
                    adapter,
                    test_df["instruction"].tolist(),
                    dict(config, device="cpu"),
                )

            prov = spec["provenance"]
            models_results[mid] = {
                "predictions": preds_df,
                "metrics": {
                    **eval_data["metrics"],
                    "core_metrics": eval_data["core_metrics"],
                    "source_mode": {
                        "predictions": "evaluated_on_test",
                        "metrics": "computed_on_test",
                        "latency": "measured",
                    },
                },
                "per_class": eval_data["per_class"],
                "confusion_matrix": eval_data["confusion_matrix"],
                "latency": bench_data,
            }

            if is_cuda_requested:
                import torch

                adapter_cuda = TransformerIntentAdapter(
                    model_dir=spec["model_dir"],
                    model_id=mid,
                    max_length=config.get("max_length", 64),
                    device="cuda",
                )
                bench_cuda = benchmark_classifier(
                    adapter_cuda,
                    test_df["instruction"].tolist(),
                    config,
                )
                models_results[mid]["latency_cuda"] = bench_cuda
                cpu_p50 = bench_data["latency"]["p50"]
                cuda_p50 = bench_cuda["latency"]["p50"]
                speedup = (cpu_p50 / cuda_p50) if cuda_p50 > 0 else 0.0

                cuda_rows.append({
                    "model_id": mid,
                    "device": "cuda",
                    "gpu_name": torch.cuda.get_device_name(0),
                    "latency_p50_ms": bench_cuda["latency"]["p50"] * 1000.0,
                    "latency_p95_ms": bench_cuda["latency"]["p95"] * 1000.0,
                    "throughput_items_sec": bench_cuda["throughput"]["items_per_second"],
                    "cpu_latency_p50_ms": cpu_p50 * 1000.0,
                    "speedup_vs_cpu": speedup,
                })

            training_samples: int | str = "unknown"
            cv_protocol = "none"
            cv_macro_f1 = np.nan
            report_file = Path(spec["model_dir"]) / "training_report.json"
            if report_file.exists():
                try:
                    rep = json.loads(report_file.read_text(encoding="utf-8"))
                    training_samples = rep.get("train_samples", "unknown")
                    cv_protocol = rep.get("cv_protocol", "none")
                    if cv_protocol == "10-fold cross-validation" and "cv_macro_f1_mean" in rep:
                        cv_macro_f1 = float(rep["cv_macro_f1_mean"])
                except Exception:
                    pass

            comp_rows.append({
                "model_id": mid,
                "candidate_id": mid,
                "model_type": "transformer",
                "origin": prov["origin"],
                "independence_status": prov["status"],
                "eligible_for_independent_ranking": prov["eligible_for_independent_ranking"],
                "is_cv_winner": False,
                "cv_macro_f1": cv_macro_f1,
                "test_macro_f1": eval_data["metrics"]["macro_f1"],
                "test_accuracy": eval_data["metrics"]["accuracy"],
                "test_weighted_f1": eval_data["metrics"]["weighted_f1"],
                "test_core_macro_f1": eval_data["core_metrics"]["macro_f1"],
                "latency_p50_ms": bench_data["latency"]["p50"] * 1000.0,
                "latency_p95_ms": bench_data["latency"]["p95"] * 1000.0,
                "throughput_items_sec": bench_data["throughput"]["items_per_second"],
                "training_samples": training_samples,
                "cv_protocol": cv_protocol,
            })

            model_registry[mid] = {
                "model_id": mid,
                "candidate_id": mid,
                "type": "transformer",
                "origin": prov["origin"],
                "base_model": prov.get("base_model"),
                "provenance_status": prov["status"],
                "eligible_for_independent_ranking": prov["eligible_for_independent_ranking"],
                "membership_evidence": prov.get("membership_evidence"),
                "notes": prov.get("notes"),
                "preprocessing": f"HF DistilBertTokenizer (truncation max_length={config.get('max_length', 64)})",
                "device": "cpu",
                "training_samples": training_samples,
                "cv_protocol": cv_protocol,
                "artifact_hashes": spec["artifact_hashes"],
            }

        # 3. Write artifacts atomically
        write_json_atomic(model_registry, run_dir / "model_registry.json")
        cmp_df = pd.DataFrame(comp_rows)
        write_csv_atomic(cmp_df, run_dir / "comparison.csv", index=False)

        intent_base = run_dir / "intent"
        robustness_base = run_dir / "robustness"
        for mid, mdata in models_results.items():
            mdir = intent_base / mid
            mdir.mkdir(parents=True, exist_ok=True)
            write_csv_atomic(mdata["predictions"], mdir / "predictions.csv", index=False)
            write_json_atomic(mdata["metrics"], mdir / "metrics.json")
            write_csv_atomic(mdata["per_class"], mdir / "per_class.csv", index=True)
            write_csv_atomic(mdata["confusion_matrix"], mdir / "confusion_matrix.csv", index=True)
            write_json_atomic(mdata["latency"], mdir / "latency.json")
            if "latency_cuda" in mdata:
                write_json_atomic(mdata["latency_cuda"], mdir / "latency_cuda.json")

            rdir = robustness_base / mid
            rdir.mkdir(parents=True, exist_ok=True)
            write_json_atomic({
                "status": "not_evaluated",
                "reason": "No independent robustness suite provided in comparison config",
            }, rdir / "status.json")

        cuda_df = None
        if cuda_rows:
            cuda_df = pd.DataFrame(cuda_rows)
            write_csv_atomic(cuda_df, run_dir / "cuda_profile.csv", index=False)

        metadata = {
            "run_id": run_id,
            "mode": "comparison",
            "timestamp": created_at,
            "device": device,
            "num_threads": num_threads,
            "winner_candidate_id": winner_cid,
            "winner_model_id": winner_mid,
        }
        report_md = _generate_comparison_markdown_report(cmp_df, model_registry, metadata, cuda_df=cuda_df)
        md_path = run_dir / "report.md"
        md_tmp = run_dir / ".report.md.tmp"
        md_tmp.write_text(report_md, encoding="utf-8")
        import os
        os.replace(md_tmp, md_path)

        # 4. Verify input tampering
        for name, path in source_paths.items():
            curr_h = compute_sha256(path)
            if curr_h != initial_inputs[name]:
                raise EvaluationError(f"Input {name} changed during comparison run")

        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json_atomic({"status": "completed", "completed_at": completed_at}, state_file)

        outputs: dict[str, str] = {}
        for file_path in sorted(run_dir.rglob("*")):
            if file_path.is_file() and file_path.name != "manifest.json":
                rel = file_path.relative_to(run_dir).as_posix()
                outputs[rel] = compute_sha256(file_path)

        manifest_data = {
            "schema_version": 1,
            "mode": "comparison",
            "run_id": run_id,
            "status": "completed",
            "created_at": created_at,
            "completed_at": completed_at,
            "device": device,
            "num_threads": num_threads,
            "baseline_training_manifest": config.get("baseline_training_manifest"),
            "historical_evaluation_manifest": config.get("historical_evaluation_manifest"),
            "inputs": initial_inputs,
            "outputs": outputs,
            "winner_locked": {
                "candidate_id": winner_cid,
                "model_id": winner_mid,
            },
        }
        write_json_atomic(manifest_data, run_dir / "manifest.json")

        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "manifest_path": str(run_dir / "manifest.json"),
            "comparison_df": cmp_df,
            "model_registry": model_registry,
        }

    except Exception as exc:
        write_json_atomic(
            {"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}},
            state_file,
        )
        if isinstance(exc, EvaluationError):
            raise
        raise EvaluationError(f"Comparison run failed: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for running model comparison benchmark."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(description="Run 5-Model Comparison Benchmark for SupportIQ.")
    parser.add_argument("--config", required=True, help="Path to comparison config JSON")
    parser.add_argument("--run-id", default=None, help="Optional run ID in DD-MM-YYYY-stt format")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Optional repository root path")
    parser.add_argument("--output-root", default="artifacts/evaluation", help="Root dir for evaluation runs")

    args = parser.parse_args(argv)

    try:
        res = run_comparison(
            config_path=args.config,
            run_id=args.run_id,
            repo_root=args.repo_root,
            output_root=args.output_root,
        )
        print("=== Comparison completed successfully! ===")
        print(f"Run dir: {res['run_dir']}")
        return 0
    except Exception as exc:
        print(f"Comparison failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
