"""Contracts, provenance registry, and historical benchmark validation for model comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.contracts import (
    VerifiedMLInputs,
    _resolve_path,
    compute_sha256,
    hash_inputs,
    load_config as load_eval_config,
    load_json,
    validate_run_id,
    verify_ml_inputs,
)

EXPECTED_COMPARISON_MODELS = {
    "multinomial_nb",
    "logistic_regression",
    "linear_svm",
    "supportiq_distilbert",
    "supportpilot_distilbert",
}

BASELINE_MODELS = {"multinomial_nb", "logistic_regression", "linear_svm"}
TRANSFORMER_MODELS = {"supportiq_distilbert", "supportpilot_distilbert"}

ALLOWED_COMPARISON_CONFIG_KEYS = {
    "schema_version",
    "seed",
    "timing",
    "metrics",
    "device",
    "num_threads",
    "max_length",
    "expected_intents",
    "n_folds",
    "baseline_training_manifest",
    "historical_evaluation_manifest",
    "models",
}


def load_comparison_config(path: str | Path, repo_root: Path | None = None) -> dict[str, Any]:
    """Load and validate comparison configuration JSON."""
    root = repo_root or Path.cwd()
    p = _resolve_path(str(path), root)
    if not p.exists():
        raise EvaluationError(f"Comparison config not found at {p}")
    try:
        data = load_json(p)
    except Exception as exc:
        raise EvaluationError(f"Failed to parse comparison config at {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise EvaluationError("Comparison config root must be a JSON object")

    unknown = set(data.keys()) - ALLOWED_COMPARISON_CONFIG_KEYS
    if unknown:
        raise EvaluationError(f"Comparison config contains unknown keys: {sorted(unknown)}")

    if data.get("schema_version") != 1:
        raise EvaluationError("schema_version must be 1")

    models = data.get("models")
    if not isinstance(models, dict):
        raise EvaluationError("models must be an object")

    model_keys = set(models.keys())
    if model_keys != EXPECTED_COMPARISON_MODELS:
        missing = EXPECTED_COMPARISON_MODELS - model_keys
        extra = model_keys - EXPECTED_COMPARISON_MODELS
        raise EvaluationError(
            f"Comparison models mismatch: missing {sorted(missing)}, extra {sorted(extra)}"
        )

    device = data.get("device", "cpu")
    if device not in {"cpu", "cuda"}:
        raise EvaluationError(f"Unsupported device: {device!r}. Must be 'cpu' or 'cuda'")

    num_threads = data.get("num_threads", 1)
    if not isinstance(num_threads, int) or num_threads <= 0:
        raise EvaluationError("num_threads must be a positive integer")

    max_length = data.get("max_length", 64)
    if not isinstance(max_length, int) or max_length <= 0:
        raise EvaluationError("max_length must be a positive integer")

    return data


def verify_comparison_inputs(
    config: dict[str, Any],
    repo_root: str | Path,
) -> dict[str, Any]:
    """Verify all inputs for comparison: baseline training, historical evaluation, and transformers."""
    root = Path(repo_root).resolve()

    # 1. Validate baseline training run using existing verify_ml_inputs
    baseline_manifest_path = config.get("baseline_training_manifest")
    if not baseline_manifest_path:
        raise EvaluationError("baseline_training_manifest must be provided")

    # Use subset of config for verify_ml_inputs
    ml_cfg = {
        "schema_version": 1,
        "seed": config.get("seed", 42),
        "timing": config.get("timing", {}),
        "expected_intents": config.get("expected_intents"),
        "n_folds": config.get("n_folds", 10),
    }
    verified_ml: VerifiedMLInputs = verify_ml_inputs(
        training_manifest=baseline_manifest_path,
        repo_root=root,
        config=ml_cfg,
    )

    test_df = verified_ml.test
    test_sample_ids = list(test_df["sample_id"].astype(str))
    test_id_to_true = dict(zip(test_sample_ids, test_df["intent"].astype(str)))

    source_paths: dict[str, Path] = dict(verified_ml.source_paths)

    # 2. Validate historical evaluation manifest
    hist_manifest_path_str = config.get("historical_evaluation_manifest")
    if not hist_manifest_path_str:
        raise EvaluationError("historical_evaluation_manifest must be provided")
    hist_path = _resolve_path(hist_manifest_path_str, root)
    if not hist_path.exists():
        raise EvaluationError(f"Historical evaluation manifest not found at {hist_path}")

    hist_man = load_json(hist_path)
    if not isinstance(hist_man, dict):
        raise EvaluationError("Historical evaluation manifest must be a JSON object")
    if hist_man.get("status") != "completed":
        raise EvaluationError(f"Historical evaluation run is not completed (status: {hist_man.get('status')!r})")

    source_paths["historical_evaluation_manifest"] = hist_path

    # Verify historical inputs match verified baseline inputs
    hist_inputs = hist_man.get("inputs", {})
    for k in ("training_manifest", "preparation_manifest", "cleaned_csv", "split_assignments", "split_report"):
        if k in hist_inputs and k in source_paths:
            expected_h = hist_inputs[k]
            actual_h = compute_sha256(source_paths[k])
            if expected_h != actual_h:
                raise EvaluationError(f"Historical manifest hash mismatch for {k}")

    hist_outputs = hist_man.get("outputs", {})
    hist_dir = hist_path.parent
    historical_results: dict[str, Any] = {
        "manifest": hist_man,
        "models": {},
        "winner_locked": hist_man.get("winner_locked"),
    }

    # Verify baseline historical predictions and metrics
    for mid in sorted(BASELINE_MODELS):
        preds_rel = f"intent/{mid}/predictions.csv"
        metrics_rel = f"intent/{mid}/metrics.json"

        if preds_rel not in hist_outputs:
            raise EvaluationError(f"Missing required historical output: {preds_rel}")
        preds_file = hist_dir / preds_rel
        if not preds_file.exists():
            raise EvaluationError(f"Historical predictions file not found: {preds_file}")
        if compute_sha256(preds_file) != hist_outputs[preds_rel]:
            raise EvaluationError(f"Hash mismatch for historical predictions {preds_rel}")

        source_paths[f"hist_{mid}_predictions"] = preds_file

        preds_df = pd.read_csv(preds_file)
        if "sample_id" not in preds_df.columns or "y_true" not in preds_df.columns or "y_pred" not in preds_df.columns:
            raise EvaluationError(f"Predictions file {preds_rel} missing required columns")

        # Check sample IDs match test set exactly
        if preds_df["sample_id"].duplicated().any():
            raise EvaluationError(f"Duplicate sample_id found in historical predictions: {preds_rel}")

        hist_sids = list(preds_df["sample_id"].astype(str))
        if set(hist_sids) != set(test_sample_ids) or len(hist_sids) != len(test_sample_ids):
            raise EvaluationError(f"Sample IDs in {preds_rel} do not match verified test set exactly")

        # Check y_true matches verified test set
        for sid, y_t in zip(preds_df["sample_id"].astype(str), preds_df["y_true"].astype(str)):
            if test_id_to_true.get(sid) != y_t:
                raise EvaluationError(f"Ground truth y_true mismatch in {preds_rel} for sample {sid}")

        metrics_data = {}
        if metrics_rel in hist_outputs:
            metrics_file = hist_dir / metrics_rel
            if metrics_file.exists() and compute_sha256(metrics_file) == hist_outputs[metrics_rel]:
                metrics_data = load_json(metrics_file)
                source_paths[f"hist_{mid}_metrics"] = metrics_file

        historical_results["models"][mid] = {
            "predictions_df": preds_df,
            "metrics": metrics_data,
        }

    # 3. Validate Transformer specs and provenance registry
    models_cfg = config.get("models", {})
    transformer_specs: dict[str, Any] = {}

    for mid in sorted(TRANSFORMER_MODELS):
        m_info = models_cfg.get(mid, {})
        model_dir_str = m_info.get("model_dir")
        if not model_dir_str:
            raise EvaluationError(f"Model {mid} missing model_dir")

        mdir = _resolve_path(model_dir_str, root)
        # Prevent path escape outside repo
        try:
            mdir.relative_to(root)
        except ValueError:
            raise EvaluationError(f"Model directory {mdir} escapes repo root")

        if not mdir.exists():
            raise EvaluationError(f"Transformer model directory not found: {mdir}")

        config_path = mdir / "config.json"
        tok_cfg_path = mdir / "tokenizer_config.json"
        tok_vocab_path = mdir / "tokenizer.json"
        weights_safetensors = mdir / "model.safetensors"
        weights_bin = mdir / "pytorch_model.bin"

        for req in (config_path, tok_cfg_path, tok_vocab_path):
            if not req.exists():
                raise EvaluationError(f"Missing required transformer artifact at {req}")

        if not weights_safetensors.exists() and not weights_bin.exists():
            raise EvaluationError(f"No weights file found in {mdir} (.safetensors or .bin)")

        weights_path = weights_safetensors if weights_safetensors.exists() else weights_bin

        source_paths[f"{mid}_config"] = config_path
        source_paths[f"{mid}_tokenizer_config"] = tok_cfg_path
        source_paths[f"{mid}_tokenizer"] = tok_vocab_path
        source_paths[f"{mid}_weights"] = weights_path

        report_path = mdir / "training_report.json"
        has_report = report_path.exists()
        if has_report:
            source_paths[f"{mid}_training_report"] = report_path

        # Provenance verification
        prov = m_info.get("provenance", {})
        origin = prov.get("origin", "unknown")
        base_model = prov.get("base_model")
        membership_evidence = prov.get("membership_evidence")

        # Explicit provenance rule: unless verified membership evidence is provided, status is unverified
        if membership_evidence and isinstance(membership_evidence, dict) and membership_evidence.get("verified") is True:
            prov_status = "verified"
            eligible_for_independent_ranking = True
        else:
            prov_status = "unverified"
            eligible_for_independent_ranking = False

        artifact_hashes = {
            "config": compute_sha256(config_path),
            "tokenizer_config": compute_sha256(tok_cfg_path),
            "tokenizer": compute_sha256(tok_vocab_path),
            "weights": compute_sha256(weights_path),
        }
        if has_report:
            artifact_hashes["training_report"] = compute_sha256(report_path)

        transformer_specs[mid] = {
            "model_id": mid,
            "model_dir": mdir,
            "artifact_hashes": artifact_hashes,
            "provenance": {
                "origin": origin,
                "base_model": base_model,
                "status": prov_status,
                "eligible_for_independent_ranking": eligible_for_independent_ranking,
                "membership_evidence": membership_evidence,
                "notes": (
                    "Verified independent test isolation"
                    if prov_status == "verified"
                    else "Unverified training split overlap risk; score is descriptive only"
                ),
            },
        }

    input_hashes = hash_inputs(source_paths)

    return {
        "test": test_df,
        "class_order": verified_ml.class_order,
        "baseline_model_dirs": verified_ml.model_dirs,
        "transformer_specs": transformer_specs,
        "historical_results": historical_results,
        "source_paths": source_paths,
        "input_hashes": input_hashes,
    }
