"""Inference bundle and atomic artifact writers for the training pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection, Sequence

import joblib
import numpy as np
import pandas as pd

from pipeline.preparation.features import IntentFeaturePipeline


@dataclass
class IntentModelBundle:
    """A fitted text transformer plus classifier with a stable inference API."""

    transformer: IntentFeaturePipeline
    classifier: Any
    model_id: str
    candidate_id: str
    classes_: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        classifier_classes = [str(value) for value in list(self.classifier.classes_)]
        if classifier_classes != list(self.classes_):
            raise ValueError(
                f"classes_: bundle classes do not match classifier classes for {self.model_id}"
            )
        self.classes_ = classifier_classes

    def _transform(self, texts: Sequence[str]) -> Any:
        return self.transformer.transform(texts)

    def predict(self, texts: Sequence[str]) -> np.ndarray:
        return self.classifier.predict(self._transform(texts))

    def decision_function(self, texts: Sequence[str]) -> np.ndarray:
        if not hasattr(self.classifier, "decision_function"):
            raise AttributeError(f"{self.model_id} does not provide decision_function")
        return self.classifier.decision_function(self._transform(texts))

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        if not hasattr(self.classifier, "predict_proba"):
            raise AttributeError(f"{self.model_id} does not provide predict_proba")
        return self.classifier.predict_proba(self._transform(texts))

    def save(self, model_dir: str | Path) -> Path:
        return save_bundle(self, model_dir)

    @classmethod
    def load(cls, model_dir: str | Path) -> "IntentModelBundle":
        return load_bundle(model_dir)


def save_bundle(bundle: IntentModelBundle, model_dir: str | Path) -> Path:
    """Write one bundle to ``model_dir/bundle.joblib`` atomically."""
    directory = Path(model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "bundle.joblib"
    temporary = directory / ".bundle.joblib.tmp"
    try:
        joblib.dump(bundle, temporary)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def load_bundle(model_dir: str | Path) -> IntentModelBundle:
    """Load a bundle from ``model_dir/bundle.joblib``."""
    target = Path(model_dir) / "bundle.joblib"
    if not target.exists():
        raise FileNotFoundError(f"Bundle not found at {target}")
    loaded = joblib.load(target)
    if not isinstance(loaded, IntentModelBundle):
        raise TypeError(f"Loaded object is {type(loaded)}, expected IntentModelBundle")
    return loaded


def write_json_atomic(data: Any, path: str | Path) -> Path:
    """Write JSON through a same-directory temporary file, then replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def write_csv_atomic(frame: pd.DataFrame, path: str | Path, *, index: bool = False) -> Path:
    """Write a DataFrame through a same-directory temporary file, then replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        frame.to_csv(temporary, index=index)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def build_model_card(
    *,
    run_id: str,
    model_id: str,
    candidate_id: str,
    params: dict[str, Any],
    resolved_params: dict[str, Any],
    cv_metrics: dict[str, Any],
    preparation_run_id: str,
    dataset_version: str,
    split_version: str,
    class_order: Sequence[str],
    core_intents: Collection[str],
    target_met: bool,
) -> dict[str, Any]:
    """Emit a model card capturing provenance, parameters, scope, and evaluation requirements."""
    classes = [str(label) for label in class_order]
    return {
        "model_id": model_id,
        "candidate_id": candidate_id,
        "params": params,
        "resolved_params": resolved_params,
        "training_run_id": run_id,
        "preparation_run_id": preparation_run_id,
        "dataset_version": dataset_version,
        "split_version": split_version,
        "language": "en",
        "languages": ["en"],
        "n_labels": len(classes),
        "classes": classes,
        "cv_metrics": cv_metrics,
        "meets_cv_target": bool(target_met),
        "core_intents": [str(label) for label in core_intents],
        "data_limitations": (
            "Trained on the synthetic Bitext Retail & E-Commerce dataset in English; "
            "real user traffic may exhibit different distributions, typos, and phrasing."
        ),
        "calibration": "not_calibrated",
        "abstention_threshold": None,
        "status": "candidate",
        "evaluation_required_before_release": True,
        "known_limits": [
            "LinearSVC does not supply probability estimates; decision_function represents uncalibrated signed distances.",
            "LogisticRegression and MultinomialNB probability outputs are not calibrated probabilities.",
            "Out-of-scope detection and confidence thresholds are not tuned during training and require evaluation protocols.",
        ],
    }
