"""Hold-out test and robustness evaluation for intent classification models."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from pipeline.training.artifacts import IntentModelBundle
from pipeline.evaluation import EvaluationError


def get_score_capability(bundle: IntentModelBundle) -> str:
    """Return the scoring capability of the underlying estimator (probability, margin, none)."""
    classifier = getattr(bundle, "classifier", None)
    if classifier is not None and hasattr(classifier, "predict_proba"):
        return "probability"
    if classifier is not None and hasattr(classifier, "decision_function"):
        return "margin"
    return "none"


def predict_rows(
    bundle: IntentModelBundle,
    rows: pd.DataFrame,
    batch_size: int = 256,
) -> pd.DataFrame:
    """Run batch inference on hold-out rows using the fitted model bundle strictly without fitting."""
    if rows.empty:
        return pd.DataFrame(columns=["sample_id", "y_true", "y_pred"])

    if "sample_id" not in rows.columns:
        raise EvaluationError("predict_rows: missing 'sample_id' column in input rows")
    if "instruction" not in rows.columns:
        raise EvaluationError("predict_rows: missing 'instruction' column in input rows")

    y_true_col = "intent" if "intent" in rows.columns else "y_true"
    if y_true_col not in rows.columns:
        raise EvaluationError("predict_rows: missing target label column ('intent' or 'y_true')")

    all_preds: list[str] = []
    classes_set = set(bundle.classes_)

    instructions = rows["instruction"].tolist()
    total = len(instructions)

    for start_idx in range(0, total, batch_size):
        batch_texts = instructions[start_idx : start_idx + batch_size]
        try:
            preds = bundle.predict(batch_texts)
        except Exception as exc:
            raise EvaluationError(f"Prediction failed on batch starting at {start_idx}: {exc}") from exc

        if len(preds) != len(batch_texts):
            raise EvaluationError(
                f"Prediction count mismatch: expected {len(batch_texts)}, got {len(preds)}"
            )

        for p in preds:
            if p is None or pd.isna(p) or str(p).strip() == "":
                raise EvaluationError("Received NaN, null, or empty string prediction")
            p_str = str(p)
            if p_str not in classes_set:
                raise EvaluationError(f"Predicted label {p_str!r} not in bundle classes")
            all_preds.append(p_str)

    return pd.DataFrame({
        "sample_id": rows["sample_id"].tolist(),
        "y_true": rows[y_true_col].astype(str).tolist(),
        "y_pred": all_preds,
    })


def classification_report_data(
    predictions: pd.DataFrame,
    class_order: Sequence[str],
    core_intents: Sequence[str],
) -> dict[str, Any]:
    """Compute overall metrics, per-class breakdown, confusion matrix, and core product metrics."""
    order_list = [str(c) for c in class_order]
    core_list = [str(c) for c in core_intents]

    y_true = predictions["y_true"].astype(str)
    y_pred = predictions["y_pred"].astype(str)

    overall_metrics = {
        "macro_f1": float(f1_score(y_true, y_pred, labels=order_list, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, labels=order_list, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
    }

    report = classification_report(
        y_true,
        y_pred,
        labels=order_list,
        output_dict=True,
        zero_division=0,
    )

    per_class_rows = []
    for label in order_list:
        metrics = report.get(label, {})
        per_class_rows.append({
            "label": label,
            "precision": float(metrics.get("precision", 0.0)),
            "recall": float(metrics.get("recall", 0.0)),
            "f1": float(metrics.get("f1-score", 0.0)),
            "support": int(metrics.get("support", 0)),
        })
    per_class_df = pd.DataFrame(per_class_rows).set_index("label")

    cm_array = confusion_matrix(y_true, y_pred, labels=order_list)
    cm_df = pd.DataFrame(cm_array, index=order_list, columns=order_list)

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

    return {
        "metrics": overall_metrics,
        "per_class": per_class_df,
        "confusion_matrix": cm_df,
        "core_metrics": core_metrics,
    }
