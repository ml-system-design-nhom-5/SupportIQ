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


def evaluate_robustness(
    bundle: IntentModelBundle,
    cases: list[dict[str, Any]],
    class_order: Sequence[str],
) -> dict[str, Any]:
    """Evaluate intent model robustness across defined slices and paired perturbations."""
    if not cases:
        return {"cases_evaluated": 0, "slices": {}, "case_details": []}

    case_map: dict[str, dict[str, Any]] = {}
    for c in cases:
        cid = c.get("case_id")
        if not cid:
            raise EvaluationError("Robustness case missing case_id")
        if not c.get("slice"):
            raise EvaluationError(f"Robustness case {cid} missing slice")
        if "instruction" not in c or not str(c["instruction"]).strip():
            raise EvaluationError(f"Robustness case {cid} missing instruction")
        if c.get("requires_paired") and not c.get("source_id"):
            raise EvaluationError(f"Robustness case {cid} requires_paired is True but source_id is missing")
        case_map[cid] = c

    # Check that any referenced source_id exists
    for cid, c in case_map.items():
        src = c.get("source_id")
        if src and src not in case_map:
            raise EvaluationError(f"Robustness case {cid} references non-existent source_id {src}")

    instructions = [case_map[cid]["instruction"] for cid in case_map]
    try:
        preds = bundle.predict(instructions)
    except Exception as exc:
        raise EvaluationError(f"Robustness prediction failed: {exc}") from exc

    if len(preds) != len(instructions):
        raise EvaluationError(
            f"Robustness prediction count mismatch: expected {len(instructions)}, got {len(preds)}"
        )

    classes_set = set(class_order) if class_order else set(bundle.classes_)
    for p in preds:
        if p is None or pd.isna(p) or str(p).strip() == "":
            raise EvaluationError("Received NaN, null, or empty string prediction in robustness")
        if str(p) not in classes_set:
            raise EvaluationError(f"Predicted label {p!r} not in class taxonomy")

    results: list[dict[str, Any]] = []
    case_results: dict[str, dict[str, Any]] = {}

    for (cid, c), pred in zip(case_map.items(), preds):
        gold = c.get("gold_intent")
        correct = (str(pred) == str(gold)) if gold is not None else None
        res_entry = {
            "case_id": cid,
            "slice": c["slice"],
            "instruction": c["instruction"],
            "gold_intent": gold,
            "y_pred": str(pred),
            "correct": correct,
            "source_id": c.get("source_id"),
            "expected_action": c.get("expected_action"),
        }
        results.append(res_entry)
        case_results[cid] = res_entry

    # Slices summary
    slice_names = sorted(set(r["slice"] for r in results))
    slices_summary: dict[str, Any] = {}

    for sname in slice_names:
        s_rows = [r for r in results if r["slice"] == sname]
        eval_rows = [r for r in s_rows if r["gold_intent"] is not None]

        acc = float(np.mean([r["correct"] for r in eval_rows])) if eval_rows else None
        action_det = "unsupported" if not eval_rows and any(r.get("expected_action") for r in s_rows) else None

        # Paired statistics
        paired_rows = [r for r in s_rows if r["source_id"]]
        if paired_rows:
            valid_pairs = [r for r in paired_rows if case_results[r["source_id"]]["correct"] is True]
            paired_denom = len(valid_pairs)
            paired_num = sum(1 for r in valid_pairs if r["correct"] is True)
            paired_acc = float(paired_num / paired_denom) if paired_denom > 0 else None
        else:
            paired_denom = 0
            paired_acc = None

        slices_summary[sname] = {
            "slice": sname,
            "total_cases": len(s_rows),
            "evaluated_cases": len(eval_rows),
            "accuracy": acc,
            "paired_denominator": paired_denom,
            "paired_conditional_accuracy": paired_acc,
            "action_detection": action_det,
        }

    return {
        "cases_evaluated": len(results),
        "slices": slices_summary,
        "case_details": results,
    }
