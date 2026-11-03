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
