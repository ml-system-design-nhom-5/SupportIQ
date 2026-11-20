"""Transformer classifier adapter for evaluation without retraining."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from pipeline.evaluation import EvaluationError


class TransformerIntentAdapter:
    """Evaluation wrapper for local fine-tuned Hugging Face transformer models."""

    def __init__(
        self,
        model_dir: str | Path,
        model_id: str,
        max_length: int = 64,
        device: str = "cpu",
    ) -> None:
        self.model_dir = Path(model_dir)
        self.model_id = model_id
        self.max_length = max_length
        self.device = device.lower()

        if self.device not in {"cpu", "cuda"}:
            raise EvaluationError(f"Unsupported device: {device!r}. Must be 'cpu' or 'cuda'")

        if self.device == "cuda" and not torch.cuda.is_available():
            raise EvaluationError("CUDA device requested but torch.cuda.is_available() is False")

        # Load tokenizer strictly from local files
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_dir,
                local_files_only=True,
                trust_remote_code=False,
            )
        except Exception as exc:
            raise EvaluationError(f"Failed to load tokenizer from {self.model_dir}: {exc}") from exc

        # Load model strictly from local files with loading_info to detect missing head weights
        try:
            load_result = AutoModelForSequenceClassification.from_pretrained(
                self.model_dir,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
                output_loading_info=True,
            )
            if isinstance(load_result, tuple):
                self.model, loading_info = load_result[0], load_result[1]
            else:
                self.model, loading_info = load_result, {}
        except Exception as exc:
            raise EvaluationError(f"Failed to load model from {self.model_dir}: {exc}") from exc

        # Validate that classification head weights were not newly/randomly initialized
        missing_keys = loading_info.get("missing_keys", []) if isinstance(loading_info, dict) else []
        critical_missing = [
            k for k in missing_keys if any(term in k for term in ("classifier", "pre_classifier", "weight", "bias"))
        ]
        if critical_missing:
            raise EvaluationError(
                f"Missing required classifier weights in checkpoint: {critical_missing}. "
                "Inference must never initialize a random classification head."
            )

        # Validate taxonomy mapping
        config = self.model.config
        id2label_raw = getattr(config, "id2label", None)
        if not id2label_raw or not isinstance(id2label_raw, dict):
            raise EvaluationError(f"Model config at {self.model_dir} is missing valid id2label mapping")

        self.id2label: dict[int, str] = {int(k): str(v) for k, v in id2label_raw.items()}
        num_classes = len(self.id2label)

        # Check contiguous indices: 0 .. num_classes-1
        expected_indices = set(range(num_classes))
        if set(self.id2label.keys()) != expected_indices:
            raise EvaluationError(
                f"id2label indices must be contiguous 0..{num_classes-1}, found: {sorted(self.id2label.keys())}"
            )

        # Check for unmapped/default LABEL_0, LABEL_1, etc.
        for idx, lbl in self.id2label.items():
            if lbl.startswith("LABEL_") and lbl[6:].isdigit():
                raise EvaluationError(f"Model config contains unmapped default label: {lbl!r} at index {idx}")

        # Check bijection (no duplicate class names)
        unique_labels = set(self.id2label.values())
        if len(unique_labels) != num_classes:
            raise EvaluationError(
                f"Duplicate labels found in id2label mapping: total {num_classes}, unique {len(unique_labels)}"
            )

        self.label2id: dict[str, int] = {v: k for k, v in self.id2label.items()}
        # Standard alphabetical class order for prediction probabilities
        self.classes_: list[str] = sorted(unique_labels)

        # Ensure model is in eval mode and moved to target device
        self.model.eval()
        if self.device != "cpu":
            self.model.to(self.device)

    def synchronize(self) -> None:
        """Explicit hardware synchronization hook before and after timing."""
        if self.device == "cuda":
            torch.cuda.synchronize()

    def predict(self, texts: Sequence[str]) -> np.ndarray:
        """Predict intent class names for a sequence of text strings."""
        if len(texts) == 0:
            return np.array([], dtype=object)

        encoded = self.tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        if self.device != "cpu":
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

        with torch.inference_mode():
            outputs = self.model(**encoded)
            logits = outputs.logits
            if not torch.isfinite(logits).all():
                raise EvaluationError("Model returned non-finite logits (NaN or Inf)")
            pred_indices = torch.argmax(logits, dim=-1).cpu().numpy()

        preds = [self.id2label[int(idx)] for idx in pred_indices]
        return np.array(preds, dtype=object)

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        """Predict class probability distribution aligned with self.classes_."""
        num_classes = len(self.classes_)
        if len(texts) == 0:
            return np.zeros((0, num_classes), dtype=np.float32)

        encoded = self.tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        if self.device != "cpu":
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

        with torch.inference_mode():
            outputs = self.model(**encoded)
            logits = outputs.logits
            if not torch.isfinite(logits).all():
                raise EvaluationError("Model returned non-finite logits (NaN or Inf)")
            hf_probs = torch.softmax(logits, dim=-1).cpu().numpy()

        # Reorder probabilities from HF id2label indexing to self.classes_ alphabetical order
        batch_size = len(texts)
        reordered = np.zeros((batch_size, num_classes), dtype=np.float32)
        for col_idx, class_name in enumerate(self.classes_):
            hf_idx = self.label2id[class_name]
            reordered[:, col_idx] = hf_probs[:, hf_idx]

        return reordered
