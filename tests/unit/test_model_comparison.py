"""Unit tests for Transformer and Baseline Comparison benchmark."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from pipeline.evaluation import EvaluationError
from pipeline.preparation.utils import compute_sha256, save_json
from pipeline.training.artifacts import IntentModelBundle
from tests.unit.test_evaluation_ml import make_eval_fixture


def make_comparison_fixture(tmp_path: Path) -> dict[str, Any]:
    """Create a complete comparison fixture with 3 baselines and 2 mock transformers."""
    fx = make_eval_fixture(tmp_path)
    eval_dir = tmp_path / "artifacts" / "evaluation" / "03-11-2026-00"
    eval_dir.mkdir(parents=True, exist_ok=True)

    test_df = fx.root / "artifacts" / "preparation" / "03-11-2026-00" / "cleaned.csv"
    splits_df = fx.root / "artifacts" / "preparation" / "03-11-2026-00" / "split_assignments.csv"
    c_df = pd.read_csv(test_df)
    s_df = pd.read_csv(splits_df)
    m_test = c_df.merge(s_df[s_df["partition"] == "test"], on="sample_id")

    eval_outputs: dict[str, str] = {}
    models = ["linear_svm", "logistic_regression", "multinomial_nb"]

    for mid in models:
        mdir = eval_dir / "intent" / mid
        mdir.mkdir(parents=True, exist_ok=True)

        preds_rows = []
        for _, row in m_test.iterrows():
            preds_rows.append({
                "sample_id": row["sample_id"],
                "y_true": row["intent"],
                "y_pred": row["intent"],
            })
        preds_df = pd.DataFrame(preds_rows)
        preds_file = mdir / "predictions.csv"
        preds_df.to_csv(preds_file, index=False)
        eval_outputs[f"intent/{mid}/predictions.csv"] = compute_sha256(preds_file)

        metrics_file = mdir / "metrics.json"
        save_json({"macro_f1": 1.0, "accuracy": 1.0}, metrics_file)
        eval_outputs[f"intent/{mid}/metrics.json"] = compute_sha256(metrics_file)

    eval_manifest_data = {
        "schema_version": 1,
        "mode": "ml",
        "run_id": "03-11-2026-00",
        "status": "completed",
        "inputs": {
            "training_manifest": compute_sha256(fx.train_manifest),
            "preparation_manifest": compute_sha256(fx.prep_manifest),
            "cleaned_csv": compute_sha256(fx.cleaned_csv),
            "split_assignments": compute_sha256(fx.splits_csv),
            "split_report": compute_sha256(fx.split_report),
        },
        "outputs": eval_outputs,
        "winner_locked": {
            "candidate_id": "linear_svm__v1",
            "model_id": "linear_svm",
            "cv_macro_f1": 0.99,
            "test_macro_f1": 1.0,
        },
    }
    eval_manifest = eval_dir / "manifest.json"
    save_json(eval_manifest_data, eval_manifest)

    # Setup mock transformer directories
    models_dir = tmp_path / "artifacts" / "models"
    siq_dir = models_dir / "trained" / "distilbert-supportiq"
    sp_dir = models_dir / "finetuned" / "supportpilot-distilbert"
    siq_dir.mkdir(parents=True, exist_ok=True)
    sp_dir.mkdir(parents=True, exist_ok=True)

    intents = sorted(m_test["intent"].unique())
    id2label = {str(i): c for i, c in enumerate(intents)}
    label2id = {c: i for i, c in enumerate(intents)}

    for t_dir in (siq_dir, sp_dir):
        save_json({
            "architectures": ["DistilBertForSequenceClassification"],
            "id2label": id2label,
            "label2id": label2id,
        }, t_dir / "config.json")
        save_json({"model_max_length": 64}, t_dir / "tokenizer_config.json")
        save_json({"version": "1.0"}, t_dir / "tokenizer.json")
        (t_dir / "model.safetensors").write_bytes(b"mock_safetensors_binary_data_for_test")

    save_json({"training_samples": 9200}, siq_dir / "training_report.json")

    config = {
        "schema_version": 1,
        "seed": 42,
        "timing": {
            "warmup_requests": 2,
            "benchmark_requests": 5,
            "latency_batch_size": 1,
            "throughput_batch_size": 4,
        },
        "device": "cpu",
        "num_threads": 2,
        "max_length": 64,
        "n_folds": 2,
        "expected_intents": intents,
        "baseline_training_manifest": str(fx.train_manifest),
        "historical_evaluation_manifest": str(eval_manifest),
        "models": {
            "multinomial_nb": {"type": "baseline"},
            "logistic_regression": {"type": "baseline"},
            "linear_svm": {"type": "baseline"},
            "supportiq_distilbert": {
                "type": "transformer",
                "model_dir": str(siq_dir),
                "provenance": {
                    "origin": "local_finetuned",
                    "base_model": "distilbert/distilbert-base-uncased",
                    "membership_evidence": None,
                },
            },
            "supportpilot_distilbert": {
                "type": "transformer",
                "model_dir": str(sp_dir),
                "provenance": {
                    "origin": "external_finetuned",
                    "base_model": "distilbert/distilbert-base-uncased",
                    "membership_evidence": None,
                },
            },
        },
    }

    return {
        "fx": fx,
        "eval_manifest": eval_manifest,
        "siq_dir": siq_dir,
        "sp_dir": sp_dir,
        "config": config,
    }


def test_historical_test_ids_match_exactly(tmp_path):
    from pipeline.evaluation.comparison_contracts import verify_comparison_inputs

    setup = make_comparison_fixture(tmp_path)
    cfg = setup["config"]

    # 1. Missing test ID in predictions
    eval_dir = setup["eval_manifest"].parent
    preds_path = eval_dir / "intent" / "linear_svm" / "predictions.csv"
    df = pd.read_csv(preds_path)
    df_short = df.iloc[:-1]  # drop one sample
    df_short.to_csv(preds_path, index=False)
    # update hash in manifest
    m = json.loads(setup["eval_manifest"].read_text(encoding="utf-8"))
    m["outputs"]["intent/linear_svm/predictions.csv"] = compute_sha256(preds_path)
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)sample.*id|missing|mismatch"):
        verify_comparison_inputs(cfg, tmp_path)

    # 2. Duplicate test ID
    df_dup = pd.concat([df, df.iloc[0:1]], ignore_index=True)
    df_dup.to_csv(preds_path, index=False)
    m["outputs"]["intent/linear_svm/predictions.csv"] = compute_sha256(preds_path)
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)duplicate"):
        verify_comparison_inputs(cfg, tmp_path)

    # 3. Matching IDs but mismatched y_true
    df_tampered = df.copy()
    df_tampered.loc[0, "y_true"] = "wrong_intent_label"
    df_tampered.to_csv(preds_path, index=False)
    m["outputs"]["intent/linear_svm/predictions.csv"] = compute_sha256(preds_path)
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)y_true|label mismatch"):
        verify_comparison_inputs(cfg, tmp_path)


def test_model_and_split_hashes_must_match_history(tmp_path):
    from pipeline.evaluation.comparison_contracts import verify_comparison_inputs

    setup = make_comparison_fixture(tmp_path)
    cfg = setup["config"]
    m = json.loads(setup["eval_manifest"].read_text(encoding="utf-8"))

    # Tamper cleaned_csv hash in historical manifest
    m["inputs"]["cleaned_csv"] = "A" * 64
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)hash mismatch"):
        verify_comparison_inputs(cfg, tmp_path)


def test_missing_provenance_is_explicit_not_verified(tmp_path):
    from pipeline.evaluation.comparison_contracts import verify_comparison_inputs

    setup = make_comparison_fixture(tmp_path)
    cfg = setup["config"]

    verified = verify_comparison_inputs(cfg, tmp_path)
    specs = verified["transformer_specs"]

    for model_id in ("supportiq_distilbert", "supportpilot_distilbert"):
        assert model_id in specs
        reg = specs[model_id]["provenance"]
        assert reg["status"] == "unverified"
        assert reg["eligible_for_independent_ranking"] is False
