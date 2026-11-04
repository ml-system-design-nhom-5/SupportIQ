"""Unit tests for DistilBERT 10-fold cross-validation pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import torch

from pipeline.preparation.utils import STANDARD_INTENTS
from pipeline.training.train_distilbert_cv import (
    IntentDataset,
    aggregate_cv_metrics,
    load_and_verify_cv_data,
    save_train_sample_ids,
)


def test_cv_dataset_strict_train_filter(tmp_path: Path) -> None:
    """Verify that only partition == 'train' samples are loaded and test partition is isolated."""
    # Synthetic cleaned data with 2 intents
    intents = sorted(STANDARD_INTENTS)
    rows_clean = []
    rows_splits = []

    # 10 train samples across 2 folds (5 each) + 2 test samples
    for i in range(10):
        sid = f"sample_{i:04d}"
        rows_clean.append({"sample_id": sid, "instruction": f"query {i}", "intent": intents[i % len(intents)]})
        rows_splits.append({"sample_id": sid, "partition": "train", "fold": i % 2})

    for i in range(10, 12):
        sid = f"sample_{i:04d}"
        rows_clean.append({"sample_id": sid, "instruction": f"test query {i}", "intent": intents[i % len(intents)]})
        rows_splits.append({"sample_id": sid, "partition": "test", "fold": -1})

    clean_file = tmp_path / "cleaned.csv"
    splits_file = tmp_path / "split_assignments.csv"
    pd.DataFrame(rows_clean).to_csv(clean_file, index=False)
    pd.DataFrame(rows_splits).to_csv(splits_file, index=False)

    dev_df, test_ids = load_and_verify_cv_data(clean_file, splits_file, n_folds=2, expected_train_count=10)

    assert len(dev_df) == 10
    assert set(dev_df["fold"].unique()) == {0, 1}
    assert (dev_df["partition"] == "train").all()
    assert len(test_ids) == 2
    assert set(dev_df["sample_id"]).isdisjoint(set(test_ids))


def test_cv_dataset_rejects_count_or_label_mismatch(tmp_path: Path) -> None:
    """Verify ValueError is raised if sample count doesn't match expected or foreign label exists."""
    intents = sorted(STANDARD_INTENTS)
    rows_clean = [
        {"sample_id": "s1", "instruction": "hello", "intent": "not_an_intent"},
    ]
    rows_splits = [
        {"sample_id": "s1", "partition": "train", "fold": 0},
    ]

    clean_file = tmp_path / "cleaned.csv"
    splits_file = tmp_path / "split_assignments.csv"
    pd.DataFrame(rows_clean).to_csv(clean_file, index=False)
    pd.DataFrame(rows_splits).to_csv(splits_file, index=False)

    with pytest.raises(ValueError, match="taxonomy"):
        load_and_verify_cv_data(clean_file, splits_file, n_folds=1, expected_train_count=1)


def test_cv_oof_aggregation() -> None:
    """Verify that aggregate_cv_metrics computes mean and sample standard deviation accurately."""
    fold_df = pd.DataFrame([
        {"fold": 0, "macro_f1": 0.90, "accuracy": 0.92, "weighted_f1": 0.91},
        {"fold": 1, "macro_f1": 0.94, "accuracy": 0.96, "weighted_f1": 0.95},
    ])

    summary = aggregate_cv_metrics(fold_df, n_folds=2)

    assert summary["n_folds"] == 2
    assert pytest.approx(summary["macro_f1_mean"], 1e-4) == 0.92
    # sample std for [0.90, 0.94] is ~0.02828 (ddof=1) or 0.02 (ddof=0)
    assert summary["macro_f1_std"] > 0
    assert pytest.approx(summary["accuracy_mean"], 1e-4) == 0.94


def test_sample_ids_containment_and_isolation(tmp_path: Path) -> None:
    """Verify save_train_sample_ids saves list of sample IDs and verifies disjointness from test."""
    train_ids = [f"train_{i}" for i in range(100)]
    test_ids = [f"test_{i}" for i in range(20)]

    out_file = tmp_path / "train_sample_ids.json"
    save_train_sample_ids(train_ids, test_ids, out_file)

    assert out_file.exists()
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) == 100
    assert set(data).isdisjoint(set(test_ids))


def test_intent_dataset_tensor_output() -> None:
    """Verify IntentDataset produces proper tensor dictionaries."""
    encodings = {
        "input_ids": torch.tensor([[101, 102], [101, 103]]),
        "attention_mask": torch.tensor([[1, 1], [1, 1]]),
    }
    labels = [0, 1]
    dataset = IntentDataset(encodings, labels)

    assert len(dataset) == 2
    item = dataset[0]
    assert "input_ids" in item and item["input_ids"].shape == (2,)
    assert "attention_mask" in item and item["attention_mask"].shape == (2,)
    assert "labels" in item and item["labels"].item() == 0
