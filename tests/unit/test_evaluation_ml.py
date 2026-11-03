from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC

from pipeline.preparation.features import IntentFeaturePipeline
from pipeline.preparation.utils import (
    CORE_PRODUCT_INTENTS,
    compute_sha256,
    save_json,
)
from pipeline.training.artifacts import IntentModelBundle, build_model_card, save_bundle
from pipeline.evaluation import EvaluationError
from pipeline.evaluation.contracts import (
    VerifiedMLInputs,
    hash_inputs,
    load_config,
    load_suite,
    validate_run_id,
    verify_ml_inputs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class EvalFixture:
    root: Path
    prep_manifest: Path
    train_manifest: Path
    cleaned_csv: Path
    splits_csv: Path
    split_report: Path
    train_dir: Path
    expected_test_ids: set[str]
    config: dict[str, Any]


def make_eval_fixture(
    tmp_path: Path,
    intents: tuple[str, ...] = ("track_order", "cancel_order", "refund_status"),
    n_folds: int = 2,
    samples_per_class: int = 2,
) -> EvalFixture:
    root = tmp_path
    prep_dir = root / "artifacts" / "preparation" / "03-11-2026-00"
    train_dir = root / "artifacts" / "training" / "03-11-2026-00"
    prep_dir.mkdir(parents=True, exist_ok=True)
    train_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    expected_test_ids: set[str] = set()

    for intent in intents:
        for fold in range(n_folds):
            for i in range(samples_per_class):
                sid = f"{intent}_f{fold}_{i}"
                rows.append({
                    "sample_id": sid,
                    "instruction": f"question for {intent} in fold {fold} sample {i}",
                    "intent": intent,
                    "category": "CAT",
                })
        test_id = f"{intent}_test_0"
        expected_test_ids.add(test_id)
        rows.append({
            "sample_id": test_id,
            "instruction": f"heldout test question for {intent}",
            "intent": intent,
            "category": "CAT",
        })

    cleaned_df = pd.DataFrame(rows)
    cleaned_csv = prep_dir / "cleaned.csv"
    cleaned_df.to_csv(cleaned_csv, index=False)

    assignments_rows: list[dict[str, Any]] = []
    for row in rows:
        sid = row["sample_id"]
        if sid.endswith("_test_0"):
            partition, fold = "test", -1
        else:
            partition = "train"
            fold = int(sid.split("_f")[1].split("_")[0])
        assignments_rows.append({"sample_id": sid, "partition": partition, "fold": fold})

    splits_df = pd.DataFrame(assignments_rows)
    splits_csv = prep_dir / "split_assignments.csv"
    splits_df.to_csv(splits_csv, index=False)

    split_report_data = {
        "cleaned_sha256": compute_sha256(cleaned_csv),
        "splits_sha256": compute_sha256(splits_csv),
        "summary": {
            "total_samples": len(cleaned_df),
            "train_samples": int((splits_df["partition"] == "train").sum()),
            "test_samples": int((splits_df["partition"] == "test").sum()),
        },
    }
    split_report = prep_dir / "split_report.json"
    save_json(split_report_data, split_report)

    prep_manifest_data = {
        "run_id": "03-11-2026-00",
        "output_artifacts": {
            "cleaned_csv": str(cleaned_csv),
            "split_assignments": str(splits_csv),
            "split_report": str(split_report),
        },
        "metadata": {
            "dataset_version": "03-11-2026-00",
            "split_version": "03-11-2026-00",
            "cleaned_samples": len(cleaned_df),
            "train_samples": split_report_data["summary"]["train_samples"],
            "test_samples": split_report_data["summary"]["test_samples"],
        },
    }
    prep_manifest = prep_dir / "manifest.json"
    save_json(prep_manifest_data, prep_manifest)

    # Train minimal bundles
    dev_df = cleaned_df[cleaned_df["sample_id"].isin(splits_df.loc[splits_df["partition"] == "train", "sample_id"])]
    pipe = IntentFeaturePipeline(min_df=1, max_features=100)
    X = pipe.fit_transform(dev_df["instruction"])
    y = dev_df["intent"]
    classes = sorted(set(y))

    models = {
        "linear_svm": LinearSVC(C=1.0, dual="auto", random_state=42).fit(X, y),
        "logistic_regression": LogisticRegression(C=1.0, solver="lbfgs", max_iter=500).fit(X, y),
        "multinomial_nb": MultinomialNB(alpha=0.1).fit(X, y),
    }

    best_per_model: dict[str, dict[str, Any]] = {}
    train_outputs: dict[str, str] = {}

    for mid, estimator in models.items():
        mdir = train_dir / "models" / mid
        mdir.mkdir(parents=True, exist_ok=True)
        cid = f"{mid}__v1"
        bundle = IntentModelBundle(
            transformer=pipe,
            classifier=estimator,
            model_id=mid,
            candidate_id=cid,
            classes_=classes,
        )
        bpath = save_bundle(bundle, mdir)
        train_outputs[f"models/{mid}/bundle.joblib"] = compute_sha256(bpath)

        score = 0.95 if mid == "linear_svm" else 0.90
        card = build_model_card(
            run_id="03-11-2026-00",
            model_id=mid,
            candidate_id=cid,
            params={"param": 1},
            resolved_params={"param": 1},
            cv_metrics={"macro_f1_mean": score, "macro_f1_std": 0.01},
            preparation_run_id="03-11-2026-00",
            dataset_version="03-11-2026-00",
            split_version="03-11-2026-00",
            class_order=classes,
            core_intents=intents,
            target_met=True,
        )
        cpath = mdir / "model_card.json"
        save_json(card, cpath)
        train_outputs[f"models/{mid}/model_card.json"] = compute_sha256(cpath)

        best_per_model[mid] = {
            "candidate_id": cid,
            "model_id": mid,
            "params": {"param": 1},
            "macro_f1_mean": score,
            "macro_f1_std": 0.01,
        }

    selection_payload = {
        "selection_metric": "macro_f1_mean",
        "tie_break": ["macro_f1_mean_desc", "macro_f1_std_asc", "config_order"],
        "cv_target_macro_f1": 0.85,
        "meets_cv_target": True,
        "best_per_model": best_per_model,
        "winner": best_per_model["linear_svm"],
    }
    sel_path = train_dir / "selection.json"
    save_json(selection_payload, sel_path)
    train_outputs["selection.json"] = compute_sha256(sel_path)

    train_manifest_data = {
        "schema_version": 1,
        "run_id": "03-11-2026-00",
        "status": "completed",
        "preparation": {
            "run_id": "03-11-2026-00",
            "manifest_path": str(prep_manifest),
            "manifest_sha256": compute_sha256(prep_manifest),
        },
        "inputs": {
            "preparation_manifest": compute_sha256(prep_manifest),
            "cleaned_csv": compute_sha256(cleaned_csv),
            "split_assignments": compute_sha256(splits_csv),
            "split_report": compute_sha256(split_report),
        },
        "outputs": train_outputs,
        "selection": selection_payload,
    }
    train_manifest = train_dir / "manifest.json"
    save_json(train_manifest_data, train_manifest)

    config = {
        "schema_version": 1,
        "seed": 42,
        "expected_intents": list(intents),
        "n_folds": n_folds,
        "timing": {
            "warmup_requests": 2,
            "benchmark_requests": 4,
            "latency_batch_size": 1,
            "throughput_batch_size": 4,
        },
        "metrics": {"zero_division": 0},
    }

    return EvalFixture(
        root=root,
        prep_manifest=prep_manifest,
        train_manifest=train_manifest,
        cleaned_csv=cleaned_csv,
        splits_csv=splits_csv,
        split_report=split_report,
        train_dir=train_dir,
        expected_test_ids=expected_test_ids,
        config=config,
    )


def test_verify_inputs_checks_lineage_and_one_to_one_join(tmp_path):
    fx = make_eval_fixture(tmp_path)
    res = verify_ml_inputs(fx.train_manifest, fx.root, fx.config)
    assert isinstance(res, VerifiedMLInputs)
    assert set(res.test["sample_id"]) == fx.expected_test_ids
    assert len(res.model_dirs) == 3
    assert res.selection["winner"]["candidate_id"] == "linear_svm__v1"


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "extra_split_id",
        "missing_split_id",
        "duplicate_split_id",
        "cleaned_hash_mismatch",
        "splits_hash_mismatch",
        "missing_file",
        "training_not_completed",
        "model_card_target_mismatch",
        "selection_winner_mismatch",
        "near_duplicate_group_crosses_partition",
    ],
)
def test_verify_inputs_rejects_tampering_and_violations(tmp_path, tamper_kind):
    fx = make_eval_fixture(tmp_path)
    if tamper_kind == "extra_split_id":
        df = pd.read_csv(fx.splits_csv)
        df = pd.concat([df, pd.DataFrame([{"sample_id": "extra_id", "partition": "test", "fold": -1}])])
        df.to_csv(fx.splits_csv, index=False)
    elif tamper_kind == "missing_split_id":
        df = pd.read_csv(fx.splits_csv)
        df.iloc[:-1].to_csv(fx.splits_csv, index=False)
    elif tamper_kind == "duplicate_split_id":
        df = pd.read_csv(fx.splits_csv)
        df = pd.concat([df, df.iloc[[0]]])
        df.to_csv(fx.splits_csv, index=False)
    elif tamper_kind == "cleaned_hash_mismatch":
        fx.cleaned_csv.write_text("tampered", encoding="utf-8")
    elif tamper_kind == "splits_hash_mismatch":
        fx.splits_csv.write_text("tampered", encoding="utf-8")
    elif tamper_kind == "missing_file":
        (fx.train_dir / "models" / "linear_svm" / "bundle.joblib").unlink()
    elif tamper_kind == "training_not_completed":
        m = json.loads(fx.train_manifest.read_text(encoding="utf-8"))
        m["status"] = "failed"
        fx.train_manifest.write_text(json.dumps(m), encoding="utf-8")
    elif tamper_kind == "model_card_target_mismatch":
        cpath = fx.train_dir / "models" / "multinomial_nb" / "model_card.json"
        card = json.loads(cpath.read_text(encoding="utf-8"))
        card["meets_cv_target"] = False  # but score 0.90 is >= 0.85
        cpath.write_text(json.dumps(card), encoding="utf-8")
        # update output hash in manifest so hash check passes, but card check fails
        m = json.loads(fx.train_manifest.read_text(encoding="utf-8"))
        m["outputs"]["models/multinomial_nb/model_card.json"] = compute_sha256(cpath)
        fx.train_manifest.write_text(json.dumps(m), encoding="utf-8")
    elif tamper_kind == "selection_winner_mismatch":
        m = json.loads(fx.train_manifest.read_text(encoding="utf-8"))
        m["selection"]["winner"]["candidate_id"] = "unknown_winner"
        fx.train_manifest.write_text(json.dumps(m), encoding="utf-8")
    elif tamper_kind == "near_duplicate_group_crosses_partition":
        df = pd.read_csv(fx.cleaned_csv)
        train_text = df.loc[df["sample_id"] == "track_order_f0_0", "instruction"].iloc[0]
        df.loc[df["sample_id"] == "track_order_test_0", "instruction"] = train_text + "!!!"
        df.to_csv(fx.cleaned_csv, index=False)
        # Update split_report cleaned hash so hash check passes, but group check fails
        rep = json.loads(fx.split_report.read_text(encoding="utf-8"))
        rep["cleaned_sha256"] = compute_sha256(fx.cleaned_csv)
        fx.split_report.write_text(json.dumps(rep), encoding="utf-8")
        m = json.loads(fx.train_manifest.read_text(encoding="utf-8"))
        m["inputs"]["cleaned_csv"] = rep["cleaned_sha256"]
        m["inputs"]["split_report"] = compute_sha256(fx.split_report)
        fx.train_manifest.write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError):
        verify_ml_inputs(fx.train_manifest, fx.root, fx.config)


def test_missing_old_absolute_path_does_not_find_same_basename(tmp_path):
    fx = make_eval_fixture(tmp_path)
    # Put a fake absolute path from another machine into prep manifest
    prep_data = json.loads(fx.prep_manifest.read_text(encoding="utf-8"))
    prep_data["output_artifacts"]["cleaned_csv"] = "C:\\Users\\OtherMachine\\SupportIQ\\cleaned.csv"
    fx.prep_manifest.write_text(json.dumps(prep_data), encoding="utf-8")
    m = json.loads(fx.train_manifest.read_text(encoding="utf-8"))
    m["preparation"]["manifest_sha256"] = compute_sha256(fx.prep_manifest)
    m["inputs"]["preparation_manifest"] = m["preparation"]["manifest_sha256"]
    fx.train_manifest.write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="not found"):
        verify_ml_inputs(fx.train_manifest, fx.root, fx.config)


@pytest.mark.parametrize("bad_run_id", ["../escape", "dir/id", "dir\\id", "", "id with space"])
def test_run_id_rejects_path_escape(bad_run_id):
    with pytest.raises(EvaluationError):
        validate_run_id(bad_run_id)


def test_config_validation_and_loading(tmp_path):
    cfg_file = tmp_path / "valid_eval.json"
    cfg_file.write_text(
        json.dumps({
            "schema_version": 1,
            "seed": 42,
            "timing": {
                "warmup_requests": 20,
                "benchmark_requests": 1000,
                "latency_batch_size": 1,
                "throughput_batch_size": 256,
            },
            "metrics": {"zero_division": 0},
        }),
        encoding="utf-8",
    )
    loaded = load_config(cfg_file)
    assert loaded["schema_version"] == 1

    bad_file = tmp_path / "bad_eval.json"
    bad_file.write_text(json.dumps({"schema_version": 1, "unknown_key": 99}), encoding="utf-8")
    with pytest.raises(EvaluationError):
        load_config(bad_file)
