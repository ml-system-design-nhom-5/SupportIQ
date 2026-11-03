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
