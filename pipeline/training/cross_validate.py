"""Per-fold cross-validation loop and out-of-fold predictions."""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Collection, Sequence

import numpy as np
import pandas as pd
import sklearn
from scipy.sparse import csr_matrix
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from pipeline.preparation.features import IntentFeaturePipeline
from pipeline.training import TrainingError
from pipeline.training.artifacts import IntentModelBundle, write_csv_atomic, write_json_atomic
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


SUMMARY_COLUMNS = [
    "model_id",
    "candidate_id",
    "params",
    "n_folds",
    "macro_f1_mean",
    "macro_f1_std",
    "accuracy_mean",
    "accuracy_std",
    "weighted_f1_mean",
    "weighted_f1_std",
    "eligible",
]


@dataclass(frozen=True)
class SelectionResult:
    """Best candidate per model and the CV winner across models."""

    best_per_model: dict[str, str]
    winner: str
    payload: dict[str, Any]


def _mean_std(series: pd.Series) -> tuple[float, float]:
    values = pd.to_numeric(series, errors="coerce").astype(float)
    if values.empty:
        return float("nan"), float("nan")
    return float(values.mean()), float(values.std(ddof=0))


def summarize_fold_metrics(
    fold_metrics: pd.DataFrame,
    candidates: Sequence[CandidateSpec],
    *,
    n_folds: int,
) -> pd.DataFrame:
    """Aggregate fold metrics to mean/std for every configured candidate."""
    rows: list[dict[str, Any]] = []
    for spec in candidates:
        subset = fold_metrics[fold_metrics["candidate_id"] == spec.candidate_id]
        macro_mean, macro_std = _mean_std(subset["macro_f1"])
        accuracy_mean, accuracy_std = _mean_std(subset["accuracy"])
        weighted_mean, weighted_std = _mean_std(subset["weighted_f1"])
        eligible = bool(
            len(subset) == n_folds
            and subset["fold"].nunique() == n_folds
            and (subset["status"] == "ok").all()
        )
        rows.append(
            {
                "model_id": spec.model_id,
                "candidate_id": spec.candidate_id,
                "params": json.dumps(spec.params, sort_keys=True, separators=(",", ":")),
                "n_folds": int(len(subset)),
                "macro_f1_mean": macro_mean,
                "macro_f1_std": macro_std,
                "accuracy_mean": accuracy_mean,
                "accuracy_std": accuracy_std,
                "weighted_f1_mean": weighted_mean,
                "weighted_f1_std": weighted_std,
                "eligible": eligible,
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS).assign(
        _order=[spec.order for spec in candidates]
    ).sort_values("_order", kind="stable").drop(columns="_order").reset_index(drop=True)


def _optional_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or pd.isna(value):
        return None
    return float(value)


def select_candidates(
    summary: pd.DataFrame,
    candidates: Sequence[CandidateSpec],
    *,
    target: float,
) -> SelectionResult:
    """Choose one candidate per model and a deterministic overall winner."""
    if summary.empty:
        raise TrainingError("no candidates available for selection")
    eligible = summary[summary["eligible"].astype(bool)]
    if eligible.empty:
        raise TrainingError("no eligible candidates for selection")

    spec_by_id = {spec.candidate_id: spec for spec in candidates}
    model_order: list[str] = []
    for spec in candidates:
        if spec.model_id not in model_order:
            model_order.append(spec.model_id)

    records = eligible.to_dict("records")

    def rank(row: dict[str, Any]) -> tuple[float, float, int]:
        candidate_id = str(row["candidate_id"])
        spec = spec_by_id.get(candidate_id)
        order = spec.order if spec is not None else 10**9
        mean = row.get("macro_f1_mean")
        std = row.get("macro_f1_std")
        mean_value = float(mean) if mean is not None and not pd.isna(mean) else float("-inf")
        std_value = float(std) if std is not None and not pd.isna(std) else float("inf")
        return (-round(mean_value, 6), round(std_value, 6), order)

    best_rows: dict[str, dict[str, Any]] = {}
    for model_id in model_order:
        model_rows = [row for row in records if row["model_id"] == model_id]
        if not model_rows:
            raise TrainingError(f"no eligible candidate for model {model_id}")
        best_rows[model_id] = min(model_rows, key=rank)

    winner_row = min(best_rows.values(), key=rank)
    best_per_model: dict[str, dict[str, Any]] = {}
    for model_id, row in best_rows.items():
        candidate_id = str(row["candidate_id"])
        spec = spec_by_id.get(candidate_id)
        best_per_model[model_id] = {
            "candidate_id": candidate_id,
            "model_id": model_id,
            "params": spec.params if spec is not None else {},
            "macro_f1_mean": _optional_float(row, "macro_f1_mean"),
            "macro_f1_std": _optional_float(row, "macro_f1_std"),
            "accuracy_mean": _optional_float(row, "accuracy_mean"),
            "weighted_f1_mean": _optional_float(row, "weighted_f1_mean"),
        }

    winner_mean = _optional_float(winner_row, "macro_f1_mean")
    payload = {
        "selection_metric": "macro_f1_mean",
        "tie_break": ["macro_f1_mean_desc", "macro_f1_std_asc", "config_order"],
        "cv_target_macro_f1": float(target),
        "meets_cv_target": bool(
            winner_mean is not None and round(winner_mean, 6) >= target
        ),
        "best_per_model": best_per_model,
        "winner": best_per_model[str(winner_row["model_id"])],
    }
    return SelectionResult(
        best_per_model={model_id: row["candidate_id"] for model_id, row in best_per_model.items()},
        winner=str(winner_row["candidate_id"]),
        payload=payload,
    )


def build_oof_reports(
    oof: pd.DataFrame,
    *,
    labels: Sequence[str],
    core_intents: Collection[str],
    report_dir: str | Path,
) -> dict[str, dict[str, Any]]:
    """Write per-model OOF reports from the fixed label universe."""
    label_list = [str(label) for label in labels]
    core_list = [str(label) for label in core_intents]
    base_dir = Path(report_dir)
    results: dict[str, dict[str, Any]] = {}

    for model_id in oof["model_id"].drop_duplicates():
        model_id = str(model_id)
        frame = oof[oof["model_id"].astype(str) == model_id]
        model_dir = base_dir / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        report = classification_report(
            frame["y_true"],
            frame["y_pred"],
            labels=label_list,
            output_dict=True,
            zero_division=0,
        )
        per_class_rows = []
        for label in label_list:
            metrics = report.get(label, {})
            per_class_rows.append(
                {
                    "label": label,
                    "precision": float(metrics.get("precision", 0.0)),
                    "recall": float(metrics.get("recall", 0.0)),
                    "f1": float(metrics.get("f1-score", 0.0)),
                    "support": int(metrics.get("support", 0)),
                }
            )
        per_class = pd.DataFrame(per_class_rows).set_index("label")
        write_csv_atomic(per_class, model_dir / "per_class_metrics.csv", index=True)

        matrix = pd.DataFrame(
            confusion_matrix(frame["y_true"], frame["y_pred"], labels=label_list),
            index=label_list,
            columns=label_list,
        )
        write_csv_atomic(matrix, model_dir / "confusion_matrix.csv", index=True)

        wrong = frame[frame["y_true"] != frame["y_pred"]]
        if wrong.empty:
            top_confusions = pd.DataFrame(columns=["y_true", "y_pred", "count"])
        else:
            top_confusions = (
                wrong.groupby(["y_true", "y_pred"])
                .size()
                .reset_index(name="count")
                .sort_values(["count", "y_true", "y_pred"], ascending=[False, True, True])
                .head(20)
            )
        write_csv_atomic(top_confusions, model_dir / "top_confusions.csv", index=False)

        per_intent: dict[str, dict[str, Any]] = {}
        for label in core_list:
            metrics = report.get(label, {})
            per_intent[label] = {
                "precision": float(metrics.get("precision", 0.0)),
                "recall": float(metrics.get("recall", 0.0)),
                "f1": float(metrics.get("f1-score", 0.0)),
                "support": int(metrics.get("support", 0)),
            }
        core_metrics = {
            "core_intents": core_list,
            "n_core_intents": len(core_list),
            "per_intent": per_intent,
            "macro_precision": float(np.mean([item["precision"] for item in per_intent.values()]))
            if per_intent
            else float("nan"),
            "macro_recall": float(np.mean([item["recall"] for item in per_intent.values()]))
            if per_intent
            else float("nan"),
            "macro_f1": float(np.mean([item["f1"] for item in per_intent.values()]))
            if per_intent
            else float("nan"),
        }
        write_json_atomic(core_metrics, model_dir / "core_intent_metrics.json")
        results[model_id] = core_metrics

    return results


def refit_final_models(
    development: pd.DataFrame,
    config: dict[str, Any],
    candidates: Sequence[CandidateSpec],
    best_per_model: dict[str, str],
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, IntentModelBundle]:
    """Fit a single TF-IDF transformer on development and refit the chosen candidates."""
    tfidf_params = dict(config["tfidf"])
    tfidf_params["ngram_range"] = tuple(tfidf_params["ngram_range"])
    transformer = IntentFeaturePipeline(**tfidf_params)
    dev_matrix = transformer.fit_transform(development["instruction"])
    if not transformer.get_feature_names():
        raise TrainingError("empty vocabulary in development data")

    spec_by_id = {spec.candidate_id: spec for spec in candidates}
    bundles: dict[str, IntentModelBundle] = {}

    for model_id, candidate_id in best_per_model.items():
        spec = spec_by_id.get(candidate_id)
        if spec is None:
            raise TrainingError(f"candidate {candidate_id!r} not found for model {model_id!r}")
        estimator = build_estimator(spec, config)
        estimator.fit(dev_matrix, development["intent"])

        resolved = getattr(estimator, "get_params", lambda **_: {})(deep=False)
        bundle_meta = {
            **(metadata or {}),
            "sklearn_version": sklearn.__version__,
            "resolved_params": resolved,
        }
        bundles[model_id] = IntentModelBundle(
            transformer=transformer,
            classifier=estimator,
            model_id=model_id,
            candidate_id=candidate_id,
            classes_=list(estimator.classes_),
            metadata=bundle_meta,
        )
    return bundles


