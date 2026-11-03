"""Training configuration validation, candidate expansion, and estimator factory."""

from __future__ import annotations

import copy
import hashlib
import inspect
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.base import BaseEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC

MODEL_ESTIMATORS: dict[str, type[BaseEstimator]] = {
    "multinomial_nb": MultinomialNB,
    "logistic_regression": LogisticRegression,
    "linear_svm": LinearSVC,
}
SUPPORTED_MODEL_IDS = frozenset(MODEL_ESTIMATORS)
ESTIMATOR_NAMES = {name: cls.__name__ for name, cls in MODEL_ESTIMATORS.items()}
TIE_BREAK_RULES = ["macro_f1_mean_desc", "macro_f1_std_asc", "config_order"]

_ALLOWED_TOP_LEVEL = {
    "schema_version",
    "seed",
    "n_folds",
    "cv_target_macro_f1",
    "tfidf",
    "models",
    "tie_break",
}
_ALLOWED_TFIDF = {"ngram_range", "max_features", "min_df", "sublinear_tf", "lowercase"}
_ALLOWED_MODEL_KEYS = {"model_id", "estimator", "grid", "fixed_params"}


@dataclass(frozen=True)
class CandidateSpec:
    """One concrete estimator configuration inside the CV grid."""

    candidate_id: str
    model_id: str
    order: int
    params: dict[str, Any]


def load_training_config(path: str | Path) -> dict[str, Any]:
    """Load a training config JSON document."""
    with Path(path).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("config: expected a JSON object")
    return config


def _require(condition: bool, field: str, message: str) -> None:
    if not condition:
        raise ValueError(f"{field}: {message}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _estimator_param_names(estimator_cls: type[BaseEstimator]) -> set[str]:
    signature = inspect.signature(estimator_cls.__init__)
    return {name for name in signature.parameters if name != "self"}


def validate_training_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a training config without mutating the caller's dict."""
    _require(isinstance(config, dict), "config", "expected an object")
    unknown = set(config) - _ALLOWED_TOP_LEVEL
    _require(not unknown, "config", f"unknown keys {sorted(unknown)}")

    normalized = copy.deepcopy(config)

    _require(normalized.get("schema_version") == 1, "schema_version", "must be 1")
    _require(_is_int(normalized.get("seed")) and normalized["seed"] >= 0, "seed", "must be an integer >= 0")
    _require(_is_int(normalized.get("n_folds")) and normalized["n_folds"] >= 2, "n_folds", "must be an integer >= 2")
    target = normalized.get("cv_target_macro_f1")
    _require(_is_number(target) and 0 < target <= 1, "cv_target_macro_f1", "must be in (0, 1]")

    tfidf = normalized.get("tfidf")
    _require(isinstance(tfidf, dict), "tfidf", "expected an object")
    unknown_tfidf = set(tfidf) - _ALLOWED_TFIDF
    _require(not unknown_tfidf, "tfidf", f"unknown keys {sorted(unknown_tfidf)}")

    ngram = tfidf.get("ngram_range")
    _require(
        isinstance(ngram, (list, tuple)) and len(ngram) == 2 and all(_is_int(v) for v in ngram),
        "tfidf.ngram_range",
        "must be a pair of integers",
    )
    _require(1 <= ngram[0] <= ngram[1], "tfidf.ngram_range", "must satisfy 1 <= low <= high")

    max_features = tfidf.get("max_features")
    _require(
        max_features is None or (_is_int(max_features) and max_features > 0),
        "tfidf.max_features",
        "must be null or a positive integer",
    )
    _require(
        _is_int(tfidf.get("min_df")) and tfidf["min_df"] > 0,
        "tfidf.min_df",
        "must be a positive integer",
    )
    for flag in ("sublinear_tf", "lowercase"):
        _require(isinstance(tfidf.get(flag), bool), f"tfidf.{flag}", "must be a boolean")

    models = normalized.get("models")
    _require(isinstance(models, list) and bool(models), "models", "must be a non-empty list")
    seen_model_ids: set[str] = set()
    for index, model in enumerate(models):
        _require(isinstance(model, dict), f"models[{index}]", "expected an object")
        unknown_model = set(model) - _ALLOWED_MODEL_KEYS
        _require(not unknown_model, f"models[{index}]", f"unknown keys {sorted(unknown_model)}")
        model_id = model.get("model_id")
        _require(
            isinstance(model_id, str) and model_id in SUPPORTED_MODEL_IDS,
            f"models[{index}].model_id",
            f"unsupported model id {model_id!r}",
        )
        _require(model_id not in seen_model_ids, f"models[{index}].model_id", "duplicate model id")
        seen_model_ids.add(model_id)

        estimator_cls = MODEL_ESTIMATORS[model_id]
        estimator_name = model.get("estimator")
        _require(
            estimator_name == ESTIMATOR_NAMES[model_id],
            f"models[{index}].estimator",
            f"must be {ESTIMATOR_NAMES[model_id]!r} for {model_id}",
        )
        param_names = _estimator_param_names(estimator_cls)

        grid = model.get("grid")
        _require(isinstance(grid, dict) and bool(grid), f"models[{index}].grid", "must be a non-empty object")
        for param, values in grid.items():
            _require(isinstance(param, str) and param in param_names, f"models[{index}].grid", f"unknown param {param!r}")
            _require(
                isinstance(values, list) and bool(values),
                f"models[{index}].grid.{param}",
                "must be a non-empty list",
            )
            for value in values:
                _require(
                    _is_number(value) and value > 0,
                    f"models[{index}].grid.{param}",
                    "values must be numeric and > 0",
                )

        fixed_params = model.get("fixed_params")
        _require(isinstance(fixed_params, dict), f"models[{index}].fixed_params", "must be an object")
        for param in fixed_params:
            _require(
                isinstance(param, str) and param in param_names,
                f"models[{index}].fixed_params",
                f"unknown param {param!r}",
            )
        overlap = set(fixed_params) & set(grid)
        _require(not overlap, f"models[{index}]", f"fixed_params overlap grid keys {sorted(overlap)}")

    _require(normalized.get("tie_break") == TIE_BREAK_RULES, "tie_break", f"must be {TIE_BREAK_RULES}")
    return normalized


def _candidate_id(model_id: str, params: dict[str, Any]) -> str:
    rendered = ",".join(f"{key}={params[key]}" for key in sorted(params))
    return f"{model_id}__{rendered}"


def expand_candidates(config: dict[str, Any]) -> list[CandidateSpec]:
    """Expand every model grid into deterministic candidate specifications."""
    candidates: list[CandidateSpec] = []
    order = 0
    for model in config["models"]:
        grid = model["grid"]
        keys = sorted(grid)
        value_lists = [grid[key] for key in keys]
        for values in itertools.product(*value_lists):
            params = dict(zip(keys, values))
            candidates.append(
                CandidateSpec(
                    candidate_id=_candidate_id(model["model_id"], params),
                    model_id=model["model_id"],
                    order=order,
                    params=params,
                )
            )
            order += 1
    return candidates


def build_estimator(spec: CandidateSpec, config: dict[str, Any]) -> BaseEstimator:
    """Build a fresh estimator instance for one candidate."""
    model = next((item for item in config["models"] if item["model_id"] == spec.model_id), None)
    if model is None:
        raise ValueError(f"model_id: {spec.model_id!r} not present in config")
    estimator_cls = MODEL_ESTIMATORS[spec.model_id]
    params = {**model["fixed_params"], **spec.params}
    return estimator_cls(**params)


def compute_config_hash(config: dict[str, Any]) -> str:
    """Hash a config using canonical JSON so key order does not matter."""
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()
