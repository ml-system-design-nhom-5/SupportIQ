from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC

from pipeline.preparation.features import IntentFeaturePipeline
from pipeline.preparation.utils import compute_sha256, load_json, save_json
from pipeline.training.models import (
    CandidateSpec,
    build_estimator,
    compute_config_hash,
    expand_candidates,
    load_training_config,
    validate_training_config,
)
from pipeline.training.artifacts import (
    IntentModelBundle,
    load_bundle,
    save_bundle,
    write_json_atomic,
)
from pipeline.training.run_training import verify_inputs

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "pipeline" / "configs" / "training.json"


def test_shipped_config_expands_to_nine_candidates():
    config = load_training_config(CONFIG_PATH)
    candidates = expand_candidates(config)
    assert [c.model_id for c in candidates] == (
        ["multinomial_nb"] * 3 + ["logistic_regression"] * 3 + ["linear_svm"] * 3
    )
    assert candidates[0].candidate_id == "multinomial_nb__alpha=0.1"
    assert config["n_folds"] == 10
    assert config["cv_target_macro_f1"] == 0.85
    assert config["seed"] == 42


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["models"].append(dict(c["models"][0])),
        lambda c: c["models"][0].update(grid={"alpha": []}),
        lambda c: c["models"][0].update(grid={"alpha": [0.0]}),
        lambda c: c["models"][0].update(model_id="random_forest"),
        lambda c: c.update(n_folds=1),
        lambda c: c["tfidf"].update(ngram_range=[2, 1]),
        lambda c: c.update(unknown_key=1),
    ],
)
def test_invalid_config_is_rejected(mutate):
    config = load_training_config(CONFIG_PATH)
    mutate(config)
    with pytest.raises(ValueError):
        validate_training_config(config)


def test_build_estimator_applies_params_and_returns_fresh_instance():
    config = load_training_config(CONFIG_PATH)
    candidates = {c.model_id: c for c in expand_candidates(config)}
    lr_a = build_estimator(candidates["logistic_regression"], config)
    lr_b = build_estimator(candidates["logistic_regression"], config)
    assert lr_a is not lr_b
    assert lr_a.get_params()["solver"] == "lbfgs"
    assert lr_a.get_params()["max_iter"] == 2000
    svm = build_estimator(candidates["linear_svm"], config)
    assert svm.get_params()["dual"] == "auto"
    assert svm.get_params()["random_state"] == 42


def test_config_hash_is_canonical_and_value_sensitive():
    assert compute_config_hash({"b": 1, "a": 2}) == compute_config_hash({"a": 2, "b": 1})
    assert compute_config_hash({"a": 2}) != compute_config_hash({"a": 3})


TEXTS = ["track my order", "cancel my order", "refund status", "where is my parcel"]
LABELS = ["track_order", "cancel_order", "refund_status", "track_order"]


def _fit_tiny_bundle(model_id="logistic_regression"):
    transformer = IntentFeaturePipeline(min_df=1, max_features=50).fit(TEXTS)
    if model_id == "linear_svm":
        classifier = LinearSVC(C=1.0, dual="auto", max_iter=5000, random_state=42)
    else:
        classifier = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
    classifier.fit(transformer.transform(TEXTS), LABELS)
    return IntentModelBundle(
        transformer=transformer,
        classifier=classifier,
        model_id=model_id,
        candidate_id=f"{model_id}__C=1.0",
        classes_=list(classifier.classes_),
        metadata={"sklearn_version": sklearn.__version__},
    )


def test_bundle_roundtrip_and_text_normalization(tmp_path):
    bundle = _fit_tiny_bundle()
    reference = bundle.predict(["track my order"]).tolist()
    assert bundle.predict(["ＴＲＡＣＫ   ＭＹ   ＯＲＤＥＲ"]).tolist() == reference
    saved = save_bundle(bundle, tmp_path / "models" / "logistic_regression")
    loaded = load_bundle(saved.parent)
    assert loaded.predict(TEXTS).tolist() == bundle.predict(TEXTS).tolist()


def test_bundle_scores_follow_classes_order():
    bundle = _fit_tiny_bundle("linear_svm")
    scores = bundle.decision_function(TEXTS)
    predicted = bundle.predict(TEXTS).tolist()
    assert predicted == [bundle.classes_[i] for i in scores.argmax(axis=1)]


def test_svm_bundle_does_not_fake_probabilities():
    bundle = _fit_tiny_bundle("linear_svm")
    with pytest.raises(AttributeError):
        bundle.predict_proba(TEXTS)


def test_atomic_json_write_replaces_without_leftovers(tmp_path):
    target = tmp_path / "run" / "run_state.json"
    write_json_atomic({"status": "running"}, target)
    write_json_atomic({"status": "completed"}, target)
    assert load_json(target) == {"status": "completed"}
    assert [p.name for p in target.parent.iterdir()] == ["run_state.json"]


@dataclass
class PrepFixture:
    root: Path
    manifest_path: Path
    cleaned_path: Path
    splits_path: Path
    report_path: Path
    cleaned: pd.DataFrame
    assignments: pd.DataFrame


def rewrite_fixture(fx: PrepFixture) -> None:
    fx.cleaned.to_csv(fx.cleaned_path, index=False)
    fx.assignments.to_csv(fx.splits_path, index=False)
    partition = fx.assignments["partition"]
    summary = {
        "total_samples": len(fx.cleaned),
        "train_samples": int((partition == "train").sum()),
        "test_samples": int((partition == "test").sum()),
    }
    report = {
        "cleaned_sha256": compute_sha256(fx.cleaned_path),
        "splits_sha256": compute_sha256(fx.splits_path),
        "summary": summary,
    }
    save_json(report, fx.report_path)
    manifest = {
        "run_id": "prep-fixture",
        "metadata": {
            "dataset_version": "03-11-2026-02",
            "split_version": "03-11-2026-02",
            "cleaned_samples": summary["total_samples"],
            "train_samples": summary["train_samples"],
            "test_samples": summary["test_samples"],
        },
        "output_artifacts": {
            "cleaned_csv": str(fx.cleaned_path),
            "split_assignments": str(fx.splits_path),
            "split_report": str(fx.report_path),
        },
    }
    save_json(manifest, fx.manifest_path)


def make_prep_fixture(
    tmp_path,
    intents=("alpha", "beta", "gamma"),
    n_folds=2,
    samples_per_class_fold=2,
) -> PrepFixture:
    rows = []
    for intent in intents:
        for fold in range(n_folds):
            for i in range(samples_per_class_fold):
                rows.append(
                    {
                        "sample_id": f"{intent}-{fold}-{i}",
                        "instruction": f"{intent} development question {fold} {i}",
                        "intent": intent,
                        "category": "CAT",
                    }
                )
        rows.append(
            {
                "sample_id": f"{intent}-test",
                "instruction": f"{intent} heldout question",
                "intent": intent,
                "category": "CAT",
            }
        )
    cleaned = pd.DataFrame(rows)
    assignments = pd.DataFrame(
        {
            "sample_id": cleaned["sample_id"],
            "partition": np.where(cleaned["sample_id"].str.endswith("-test"), "test", "train"),
            "fold": cleaned["sample_id"].str.extract(r"-(\d+)-\d+$")[0].astype("Int64").fillna(-1).astype(int),
        }
    )
    cleaned_path = tmp_path / "cleaned.csv"
    splits_path = tmp_path / "split_assignments.csv"
    report_path = tmp_path / "split_report.json"
    manifest_path = tmp_path / "manifest.json"
    cleaned.to_csv(cleaned_path, index=False)
    assignments.to_csv(splits_path, index=False)
    fx = PrepFixture(tmp_path, manifest_path, cleaned_path, splits_path, report_path, cleaned, assignments)
    rewrite_fixture(fx)
    return fx


def test_verify_inputs_returns_development_only(tmp_path):
    fx = make_prep_fixture(tmp_path)
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    assert len(verified.development) == 12
    assert len(verified.test_sample_ids) == 3
    assert set(verified.development["sample_id"]).isdisjoint(verified.test_sample_ids)
    assert verified.class_order == ("alpha", "beta", "gamma")


def test_verify_inputs_returns_no_test_text(tmp_path):
    fx = make_prep_fixture(tmp_path)
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    test_text = set(fx.cleaned.loc[fx.cleaned["sample_id"].str.endswith("-test"), "instruction"])
    assert test_text.isdisjoint(set(verified.development["instruction"]))


def test_verify_inputs_rejects_checksum_mismatch(tmp_path):
    fx = make_prep_fixture(tmp_path)
    report = load_json(fx.report_path)
    report["cleaned_sha256"] = "0" * 64
    save_json(report, fx.report_path)
    with pytest.raises(ValueError, match="cleaned_sha256"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


@pytest.mark.parametrize("break_ids", ["missing", "duplicate", "extra"])
def test_verify_inputs_rejects_bad_id_coverage(tmp_path, break_ids):
    fx = make_prep_fixture(tmp_path)
    if break_ids == "missing":
        fx.assignments = fx.assignments.iloc[:-1]
    elif break_ids == "duplicate":
        fx.assignments = pd.concat([fx.assignments, fx.assignments.iloc[[0]]])
    else:
        extra = fx.assignments.iloc[[0]].assign(sample_id="not-in-cleaned")
        fx.assignments = pd.concat([fx.assignments, extra])
    rewrite_fixture(fx)
    with pytest.raises(ValueError):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_count_mismatch(tmp_path):
    fx = make_prep_fixture(tmp_path)
    manifest = load_json(fx.manifest_path)
    manifest["metadata"]["train_samples"] += 1
    save_json(manifest, fx.manifest_path)
    with pytest.raises(ValueError, match="train_samples"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def _fold_column(fx, fold):
    fx.assignments.loc[fx.assignments["fold"] == fold, "fold"] = 99
    rewrite_fixture(fx)


def test_verify_inputs_rejects_test_fold_not_minus_one(tmp_path):
    fx = make_prep_fixture(tmp_path)
    fx.assignments.loc[fx.assignments["partition"] == "test", "fold"] = 0
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="test.*fold"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_missing_or_empty_fold(tmp_path):
    fx = make_prep_fixture(tmp_path)
    _fold_column(fx, 1)
    with pytest.raises(ValueError, match="fold"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_intent_missing_from_fold_validation(tmp_path):
    fx = make_prep_fixture(tmp_path)
    mask = (fx.cleaned["intent"] == "gamma") & fx.cleaned["sample_id"].isin(
        fx.assignments.loc[fx.assignments["fold"] == 1, "sample_id"]
    )
    fx.assignments.loc[fx.assignments["sample_id"].isin(fx.cleaned.loc[mask, "sample_id"]), "fold"] = 0
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="validation fold 1"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_near_duplicate_group_across_folds(tmp_path):
    fx = make_prep_fixture(tmp_path)
    fold0_id = fx.assignments.loc[fx.assignments["fold"] == 0, "sample_id"].iloc[0]
    fold1_id = fx.assignments.loc[fx.assignments["fold"] == 1, "sample_id"].iloc[0]
    text = fx.cleaned.loc[fx.cleaned["sample_id"] == fold0_id, "instruction"].iloc[0]
    fx.cleaned.loc[fx.cleaned["sample_id"] == fold1_id, "instruction"] = text.upper() + "!!!"
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="group"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_conflicting_group_labels(tmp_path):
    fx = make_prep_fixture(tmp_path)
    first, second = fx.assignments["sample_id"].iloc[0], fx.assignments["sample_id"].iloc[1]
    text = fx.cleaned.loc[fx.cleaned["sample_id"] == first, "instruction"].iloc[0]
    fx.cleaned.loc[fx.cleaned["sample_id"] == second, "instruction"] = text
    fx.cleaned.loc[fx.cleaned["sample_id"] == second, "intent"] = "beta"
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="conflicting"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
