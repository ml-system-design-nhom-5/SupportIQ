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


def test_core_precision_keeps_false_positives_from_other_labels():
    from pipeline.evaluation.evaluate_intent import classification_report_data

    # gold [A, B], pred [A, A], core [A] -> A has 1 TP, 1 FP -> precision=0.5, recall=1.0, f1=2/3
    preds = pd.DataFrame({
        "sample_id": ["s1", "s2"],
        "y_true": ["A", "B"],
        "y_pred": ["A", "A"],
    })
    classes = ["A", "B"]
    core = ["A"]
    res = classification_report_data(preds, class_order=classes, core_intents=core)

    core_a = res["core_metrics"]["per_intent"]["A"]
    assert core_a["precision"] == pytest.approx(0.5)
    assert core_a["recall"] == pytest.approx(1.0)
    assert core_a["f1"] == pytest.approx(2.0 / 3.0)

    # confusion matrix: rows are true, cols are pred
    cm = res["confusion_matrix"]
    assert cm.loc["A", "A"] == 1
    assert cm.loc["A", "B"] == 0
    assert cm.loc["B", "A"] == 1
    assert cm.loc["B", "B"] == 0


def test_predict_uses_bundle_without_fit(tmp_path, monkeypatch):
    from pipeline.evaluation.evaluate_intent import predict_rows

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")

    def forbidden_fit(*args, **kwargs):
        raise AssertionError("fit/fit_transform must not be called during evaluation")

    monkeypatch.setattr(IntentFeaturePipeline, "fit", forbidden_fit)
    monkeypatch.setattr(IntentFeaturePipeline, "fit_transform", forbidden_fit)

    test_df = fx.cleaned_csv
    test_rows = pd.read_csv(test_df).head(5)
    res = predict_rows(bundle, test_rows, batch_size=2)

    assert len(res) == len(test_rows)
    assert list(res["sample_id"]) == list(test_rows["sample_id"])
    assert "y_pred" in res.columns
    assert "y_true" in res.columns


@pytest.mark.parametrize("bad_scenario", ["short_output", "unknown_label", "nan_prediction"])
def test_predict_rows_validates_predictions(tmp_path, monkeypatch, bad_scenario):
    from pipeline.evaluation.evaluate_intent import predict_rows

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")
    test_rows = pd.read_csv(fx.cleaned_csv).head(4)

    if bad_scenario == "short_output":
        monkeypatch.setattr(bundle, "predict", lambda texts: np.array(["track_order"]))
    elif bad_scenario == "unknown_label":
        monkeypatch.setattr(bundle, "predict", lambda texts: np.array(["non_existent_label"] * len(texts)))
    elif bad_scenario == "nan_prediction":
        monkeypatch.setattr(bundle, "predict", lambda texts: np.array([None] * len(texts)))

    with pytest.raises(EvaluationError):
        predict_rows(bundle, test_rows, batch_size=2)


def test_svm_score_capability_is_margin_not_probability(tmp_path):
    from pipeline.evaluation.evaluate_intent import get_score_capability

    fx = make_eval_fixture(tmp_path)
    bundle_svm = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")
    bundle_lr = IntentModelBundle.load(fx.train_dir / "models" / "logistic_regression")

    assert get_score_capability(bundle_svm) == "margin"
    assert get_score_capability(bundle_lr) == "probability"


def test_robustness_separates_known_noncore_and_ood(tmp_path):
    from pipeline.evaluation.evaluate_intent import evaluate_robustness

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")

    cases = [
        # Known in-scope case
        {
            "case_id": "c1",
            "slice": "casing",
            "instruction": "TRACK MY ORDER PLEASE",
            "gold_intent": "track_order",
            "expected_action": None,
        },
        # OOD case with null gold
        {
            "case_id": "c2",
            "slice": "out_of_scope",
            "instruction": "What is the weather in Hanoi?",
            "gold_intent": None,
            "expected_action": "escalate",
        },
    ]

    res = evaluate_robustness(bundle, cases, fx.config["expected_intents"])
    assert "casing" in res["slices"]
    assert "out_of_scope" in res["slices"]
    assert res["slices"]["out_of_scope"]["accuracy"] is None
    assert res["slices"]["out_of_scope"]["action_detection"] == "unsupported"


def test_paired_robustness_denominator(tmp_path):
    from pipeline.evaluation.evaluate_intent import evaluate_robustness

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")

    cases = [
        # Base case correctly predicted
        {
            "case_id": "base_1",
            "slice": "base",
            "instruction": "question for track_order in fold 0 sample 0",
            "gold_intent": "track_order",
        },
        # Paired variant correctly predicted
        {
            "case_id": "pert_1",
            "slice": "typo",
            "instruction": "QUESTION FOR TRACK_ORDER IN FOLD 0 SAMPLE 0",
            "gold_intent": "track_order",
            "source_id": "base_1",
        },
        # Base case incorrectly predicted (cancel_order mapped to wrong gold)
        {
            "case_id": "base_2",
            "slice": "base",
            "instruction": "cancel my order",
            "gold_intent": "wrong_expected_label",
        },
        # Paired variant of base_2
        {
            "case_id": "pert_2",
            "slice": "typo",
            "instruction": "cancle my order",
            "gold_intent": "wrong_expected_label",
            "source_id": "base_2",
        },
    ]

    res = evaluate_robustness(bundle, cases, fx.config["expected_intents"])
    typo_slice = res["slices"]["typo"]
    # Denominator for conditional correctness only includes base_1 (base_2 failed)
    assert typo_slice["paired_denominator"] == 1


def test_timing_excludes_warmup_and_counts_requests(tmp_path):
    from pipeline.evaluation.benchmark import benchmark_classifier

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")

    # Mock clock: returns increasing timestamps
    # warmup=2, requests=4 -> total 6 calls
    times = [0.0, 0.05, 0.10, 0.12, 0.15, 0.19, 0.24, 0.30, 0.37, 0.45, 0.54, 0.64]
    clock_idx = 0

    def fake_clock():
        nonlocal clock_idx
        val = times[clock_idx]
        clock_idx += 1
        return val

    config = {
        "timing": {
            "warmup_requests": 2,
            "benchmark_requests": 4,
            "latency_batch_size": 1,
            "throughput_batch_size": 4,
        }
    }

    res = benchmark_classifier(bundle, ["track my order", "refund status"], config, clock=fake_clock)
    assert res["latency"]["requests_measured"] == 4
    assert res["latency"]["p50"] > 0
    assert len(res["latency"]["durations_seconds"]) == 4


def test_empty_latency_input_rejected(tmp_path):
    from pipeline.evaluation.benchmark import benchmark_classifier

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")

    with pytest.raises(EvaluationError):
        benchmark_classifier(bundle, [], fx.config)


def test_robustness_missing_source_id_rejected(tmp_path):
    from pipeline.evaluation.evaluate_intent import evaluate_robustness

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")

    cases = [
        {
            "case_id": "p1",
            "slice": "paired_typo",
            "instruction": "trak my ordr",
            "gold_intent": "track_order",
            "requires_paired": True,
            # missing source_id!
        }
    ]
    with pytest.raises(EvaluationError):
        evaluate_robustness(bundle, cases, fx.config["expected_intents"])


def test_ml_runner_keeps_cv_winner_when_test_ranking_changes(tmp_path, monkeypatch):
    from pipeline.evaluation.run_evaluation import run_ml_evaluation

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)

    # In fx, winner is linear_svm__v1. We run evaluation and check that baseline_comparison.csv
    # records is_cv_winner=True for linear_svm and False for multinomial_nb.
    out_root = tmp_path / "artifacts" / "evaluation"
    res = run_ml_evaluation(
        training_manifest=fx.train_manifest,
        suite=None,
        config_path=cfg_file,
        run_id="03-11-2026-eval-01",
        repo_root=fx.root,
        output_root=out_root,
    )
    run_dir = Path(res["run_dir"])
    comp = pd.read_csv(run_dir / "baseline_comparison.csv")

    svm_row = comp[comp["model_id"] == "linear_svm"].iloc[0]
    nb_row = comp[comp["model_id"] == "multinomial_nb"].iloc[0]
    assert svm_row["is_cv_winner"] == True
    assert nb_row["is_cv_winner"] == False


def test_ml_only_does_not_pass_system_requirements(tmp_path):
    from pipeline.evaluation.run_evaluation import run_ml_evaluation

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)

    out_root = tmp_path / "artifacts" / "evaluation"
    res = run_ml_evaluation(
        training_manifest=fx.train_manifest,
        suite=None,
        config_path=cfg_file,
        run_id="03-11-2026-eval-02",
        repo_root=fx.root,
        output_root=out_root,
    )
    run_dir = Path(res["run_dir"])
    req = pd.read_csv(run_dir / "requirements_matrix.csv")

    # System requirements must be "not_evaluated"
    system_items = req[req["requirement"].str.contains("Retrieval|Grounding|Oversight|Reliability", case=False)]
    assert (system_items["status"] == "not_evaluated").all()


def test_failed_run_has_no_completed_manifest(tmp_path, monkeypatch):
    from pipeline.evaluation.run_evaluation import run_ml_evaluation

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)

    def boom(*args, **kwargs):
        raise EvaluationError("Forced failure during prediction")

    monkeypatch.setattr("pipeline.evaluation.run_evaluation.predict_rows", boom)

    out_root = tmp_path / "artifacts" / "evaluation"
    with pytest.raises(EvaluationError, match="Forced failure"):
        run_ml_evaluation(
            training_manifest=fx.train_manifest,
            suite=None,
            config_path=cfg_file,
            run_id="03-11-2026-eval-fail",
            repo_root=fx.root,
            output_root=out_root,
        )

    run_dir = out_root / "03-11-2026-eval-fail"
    assert (run_dir / "run_state.json").exists()
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert not (run_dir / "manifest.json").exists()


def test_existing_run_is_not_modified(tmp_path):
    from pipeline.evaluation.run_evaluation import run_ml_evaluation

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)

    out_root = tmp_path / "artifacts" / "evaluation"
    existing_dir = out_root / "03-11-2026-eval-exist"
    existing_dir.mkdir(parents=True)
    sentinel = existing_dir / "sentinel.txt"
    sentinel.write_text("protected", encoding="utf-8")

    with pytest.raises(EvaluationError):
        run_ml_evaluation(
            training_manifest=fx.train_manifest,
            suite=None,
            config_path=cfg_file,
            run_id="03-11-2026-eval-exist",
            repo_root=fx.root,
            output_root=out_root,
        )
    assert sentinel.read_text(encoding="utf-8") == "protected"


def test_input_changed_midrun_fails(tmp_path, monkeypatch):
    from pipeline.evaluation.run_evaluation import run_ml_evaluation
    import pipeline.evaluation.run_evaluation as run_eval

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)

    orig_predict = run_eval.predict_rows

    def tamper_then_predict(*args, **kwargs):
        # Mutate cleaned.csv while evaluation is in-flight
        fx.cleaned_csv.write_text("corrupted mid-run", encoding="utf-8")
        return orig_predict(*args, **kwargs)

    monkeypatch.setattr("pipeline.evaluation.run_evaluation.predict_rows", tamper_then_predict)

    out_root = tmp_path / "artifacts" / "evaluation"
    with pytest.raises(EvaluationError, match="changed during run"):
        run_ml_evaluation(
            training_manifest=fx.train_manifest,
            suite=None,
            config_path=cfg_file,
            run_id="03-11-2026-eval-midrun",
            repo_root=fx.root,
            output_root=out_root,
        )


def test_cli_ml_end_to_end_writes_reloadable_report(tmp_path):
    from pipeline.evaluation.run_evaluation import main

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    argv = [
        "--mode", "ml",
        "--training-manifest", str(fx.train_manifest),
        "--config", str(cfg_file),
        "--run-id", "03-11-2026-eval-cli",
        "--output-root", str(out_root),
    ]
    rc = main(argv)
    assert rc == 0

    run_dir = out_root / "03-11-2026-eval-cli"
    man = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert man["status"] == "completed"

    for rel, digest in man["outputs"].items():
        assert compute_sha256(run_dir / rel) == digest


def test_cli_reports_failure_exit_code(tmp_path):
    from pipeline.evaluation.run_evaluation import main

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    # Provide a non-existent training manifest
    argv = [
        "--mode", "ml",
        "--training-manifest", str(tmp_path / "non_existent.json"),
        "--config", str(cfg_file),
        "--run-id", "03-11-2026-eval-err",
        "--output-root", str(out_root),
    ]
    rc = main(argv)
    assert rc == 1


def test_run_from_directory_with_spaces(tmp_path):
    from pipeline.evaluation.run_evaluation import main

    spaced_dir = tmp_path / "Dir With Spaces"
    spaced_dir.mkdir(parents=True)
    fx = make_eval_fixture(spaced_dir)
    cfg_file = spaced_dir / "eval_config.json"
    save_json(fx.config, cfg_file)
    out_root = spaced_dir / "artifacts" / "evaluation"

    argv = [
        "--mode", "ml",
        "--training-manifest", str(fx.train_manifest),
        "--config", str(cfg_file),
        "--run-id", "03-11-2026-eval-sp",
        "--output-root", str(out_root),
    ]
    rc = main(argv)
    assert rc == 0


def test_verify_inputs_rejects_missing_bundle_checksum_in_manifest_outputs(tmp_path):
    fx = make_eval_fixture(tmp_path)
    m = json.loads(fx.train_manifest.read_text(encoding="utf-8"))
    # Delete bundle output checksum
    del m["outputs"]["models/linear_svm/bundle.joblib"]
    fx.train_manifest.write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="Missing required checksum.*bundle"):
        verify_ml_inputs(fx.train_manifest, fx.root, fx.config)


def test_verify_inputs_rejects_selection_winner_tampered_from_disk_selection(tmp_path):
    fx = make_eval_fixture(tmp_path)
    m = json.loads(fx.train_manifest.read_text(encoding="utf-8"))
    # Tamper winner in training manifest selection while selection.json on disk remains unchanged
    m["selection"]["winner"] = m["selection"]["best_per_model"]["multinomial_nb"]
    fx.train_manifest.write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="selection"):
        verify_ml_inputs(fx.train_manifest, fx.root, fx.config)


def test_run_evaluation_detects_suite_and_config_tampering_midrun(tmp_path, monkeypatch):
    from pipeline.evaluation.run_evaluation import run_ml_evaluation
    import pipeline.evaluation.run_evaluation as run_eval

    fx = make_eval_fixture(tmp_path)
    cfg_file = tmp_path / "eval_config.json"
    save_json(fx.config, cfg_file)

    suite_file = tmp_path / "suite.json"
    save_json({
        "robustness_cases": [
            {
                "case_id": "c1",
                "slice": "casing",
                "instruction": "track my order",
                "gold_intent": "track_order",
            }
        ]
    }, suite_file)

    orig_predict = run_eval.predict_rows

    def tamper_config_and_suite(*args, **kwargs):
        # Tamper config and suite during prediction
        cfg_file.write_text(json.dumps({"tampered": True}), encoding="utf-8")
        suite_file.write_text(json.dumps({"tampered": True}), encoding="utf-8")
        return orig_predict(*args, **kwargs)

    monkeypatch.setattr("pipeline.evaluation.run_evaluation.predict_rows", tamper_config_and_suite)

    out_root = tmp_path / "artifacts" / "evaluation"
    with pytest.raises(EvaluationError, match="changed during run"):
        run_ml_evaluation(
            training_manifest=fx.train_manifest,
            suite=suite_file,
            config_path=cfg_file,
            run_id="03-11-2026-eval-midrun-cfg",
            repo_root=fx.root,
            output_root=out_root,
        )


def test_evaluate_robustness_validates_prediction_length_and_labels(tmp_path, monkeypatch):
    from pipeline.evaluation.evaluate_intent import evaluate_robustness

    fx = make_eval_fixture(tmp_path)
    bundle = IntentModelBundle.load(fx.train_dir / "models" / "linear_svm")

    cases = [
        {"case_id": "c1", "slice": "s1", "instruction": "test 1"},
        {"case_id": "c2", "slice": "s1", "instruction": "test 2"},
    ]

    # Classifier returns short predictions (1 instead of 2)
    monkeypatch.setattr(bundle, "predict", lambda texts: np.array(["track_order"]))
    with pytest.raises(EvaluationError, match="mismatch"):
        evaluate_robustness(bundle, cases, fx.config["expected_intents"])

    # Classifier returns unknown label
    monkeypatch.setattr(bundle, "predict", lambda texts: np.array(["unknown_label", "unknown_label"]))
    with pytest.raises(EvaluationError, match="taxonomy"):
        evaluate_robustness(bundle, cases, fx.config["expected_intents"])


def test_verify_inputs_defaults_to_standard_intents_and_checks_coverage(tmp_path):
    fx = make_eval_fixture(tmp_path)
    config_prod = dict(fx.config)
    # Remove expected_intents so it defaults to STANDARD_INTENTS
    del config_prod["expected_intents"]

    # fx only has 3 intents, but STANDARD_INTENTS requires 46 -> must fail with missing classes
    with pytest.raises(EvaluationError, match="missing expected taxonomy labels"):
        verify_ml_inputs(fx.train_manifest, fx.root, config_prod)
