"""Per-fold cross-validation loop and out-of-fold predictions."""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, f1_score

from pipeline.preparation.features import IntentFeaturePipeline
from pipeline.training import TrainingError
from pipeline.training.models import CandidateSpec, build_estimator

FOLD_METRIC_COLUMNS = [
    "model_id",
    "candidate_id",
    "params",
    "fold",
    "n_train",
    "n_validation",
    "macro_f1",
    "accuracy",
    "weighted_f1",
    "transform_seconds",
    "fit_seconds",
    "predict_seconds",
    "status",
    "warnings",
]
OOF_COLUMNS = ["sample_id", "fold", "y_true", "y_pred", "model_id", "candidate_id"]


@dataclass(frozen=True)
class CVResult:
    """Fold-level metrics and out-of-fold predictions for every candidate."""

    fold_metrics: pd.DataFrame
    oof_predictions: pd.DataFrame


def build_fold_features(
    train_texts: Sequence[str],
    validation_texts: Sequence[str],
    tfidf_config: dict[str, Any],
) -> tuple[IntentFeaturePipeline, csr_matrix, csr_matrix, float]:
    """Fit a fresh TF-IDF transformer on one training fold and transform both splits."""
    params = dict(tfidf_config)
    params["ngram_range"] = tuple(params["ngram_range"])
    transformer = IntentFeaturePipeline(**params)

    start = time.perf_counter()
    try:
        train_matrix = transformer.fit_transform(train_texts)
    except ValueError as exc:
        raise TrainingError(f"empty vocabulary in training fold: {exc}") from exc
    validation_matrix = transformer.transform(validation_texts)
    elapsed = time.perf_counter() - start

    if not transformer.get_feature_names():
        raise TrainingError("empty vocabulary in training fold")
    return transformer, train_matrix, validation_matrix, elapsed


def _failed_fold_row(
    spec: CandidateSpec,
    fold: int,
    n_train: int,
    n_validation: int,
    transform_seconds: float,
    message: str,
) -> dict[str, Any]:
    return {
        "model_id": spec.model_id,
        "candidate_id": spec.candidate_id,
        "params": json.dumps(spec.params, sort_keys=True, separators=(",", ":")),
        "fold": fold,
        "n_train": n_train,
        "n_validation": n_validation,
        "macro_f1": np.nan,
        "accuracy": np.nan,
        "weighted_f1": np.nan,
        "transform_seconds": transform_seconds,
        "fit_seconds": np.nan,
        "predict_seconds": np.nan,
        "status": "failed",
        "warnings": message,
    }


def run_cross_validation(
    development: pd.DataFrame,
    config: dict[str, Any],
    candidates: Sequence[CandidateSpec],
    *,
    class_order: Sequence[str],
    on_fold: Callable[[pd.DataFrame], None] | None = None,
) -> CVResult:
    """Run every candidate on every development fold without touching hold-out data."""
    n_folds = int(config["n_folds"])
    folds = sorted(int(value) for value in development["fold"].unique())
    if folds != list(range(n_folds)):
        raise TrainingError(f"development folds must be exactly 0..{n_folds - 1}, found {folds}")

    labels = list(class_order)
    metric_rows: list[dict[str, Any]] = []
    oof_rows: list[dict[str, Any]] = []

    for fold in range(n_folds):
        train_rows = development[development["fold"] != fold]
        validation_rows = development[development["fold"] == fold]
        if train_rows.empty or validation_rows.empty:
            raise TrainingError(f"fold {fold} has an empty train or validation split")

        _, train_matrix, validation_matrix, transform_seconds = build_fold_features(
            train_rows["instruction"].tolist(),
            validation_rows["instruction"].tolist(),
            config["tfidf"],
        )

        for spec in candidates:
            estimator = build_estimator(spec, config)
            fit_start = time.perf_counter()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                estimator.fit(train_matrix, train_rows["intent"])
            fit_seconds = time.perf_counter() - fit_start

            convergence = [
                warning for warning in caught if issubclass(warning.category, ConvergenceWarning)
            ]
            if convergence:
                message = "ConvergenceWarning: " + "; ".join(str(item.message) for item in convergence)
                metric_rows.append(
                    _failed_fold_row(
                        spec, fold, len(train_rows), len(validation_rows), transform_seconds, message
                    )
                )
                if on_fold is not None:
                    on_fold(pd.DataFrame(metric_rows, columns=FOLD_METRIC_COLUMNS))
                raise TrainingError(message)

            predict_start = time.perf_counter()
            predictions = estimator.predict(validation_matrix)
            predict_seconds = time.perf_counter() - predict_start

            macro_f1 = float(
                f1_score(
                    validation_rows["intent"],
                    predictions,
                    labels=labels,
                    average="macro",
                    zero_division=0,
                )
            )
            weighted_f1 = float(
                f1_score(
                    validation_rows["intent"],
                    predictions,
                    labels=labels,
                    average="weighted",
                    zero_division=0,
                )
            )
            accuracy = float(accuracy_score(validation_rows["intent"], predictions))

            values = (macro_f1, weighted_f1, accuracy)
            if not all(np.isfinite(value) for value in values):
                message = f"NaN metric for {spec.candidate_id} fold {fold}"
                row = _failed_fold_row(
                    spec, fold, len(train_rows), len(validation_rows), transform_seconds, message
                )
                row.update(
                    {
                        "macro_f1": macro_f1,
                        "accuracy": accuracy,
                        "weighted_f1": weighted_f1,
                        "fit_seconds": fit_seconds,
                        "predict_seconds": predict_seconds,
                    }
                )
                metric_rows.append(row)
                if on_fold is not None:
                    on_fold(pd.DataFrame(metric_rows, columns=FOLD_METRIC_COLUMNS))
                raise TrainingError(message)

            metric_rows.append(
                {
                    "model_id": spec.model_id,
                    "candidate_id": spec.candidate_id,
                    "params": json.dumps(spec.params, sort_keys=True, separators=(",", ":")),
                    "fold": fold,
                    "n_train": len(train_rows),
                    "n_validation": len(validation_rows),
                    "macro_f1": macro_f1,
                    "accuracy": accuracy,
                    "weighted_f1": weighted_f1,
                    "transform_seconds": transform_seconds,
                    "fit_seconds": fit_seconds,
                    "predict_seconds": predict_seconds,
                    "status": "ok",
                    "warnings": "; ".join(str(item.message) for item in caught),
                }
            )
            oof_rows.extend(
                {
                    "sample_id": sample_id,
                    "fold": fold,
                    "y_true": y_true,
                    "y_pred": y_pred,
                    "model_id": spec.model_id,
                    "candidate_id": spec.candidate_id,
                }
                for sample_id, y_true, y_pred in zip(
                    validation_rows["sample_id"], validation_rows["intent"], predictions
                )
            )

        if on_fold is not None:
            on_fold(pd.DataFrame(metric_rows, columns=FOLD_METRIC_COLUMNS))

    return CVResult(
        fold_metrics=pd.DataFrame(metric_rows, columns=FOLD_METRIC_COLUMNS),
        oof_predictions=pd.DataFrame(oof_rows, columns=OOF_COLUMNS),
    )
