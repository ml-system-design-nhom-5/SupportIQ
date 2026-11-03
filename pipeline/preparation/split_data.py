"""Data partitioning module with Stratified Group K-Fold and leakage verification."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from pipeline.preparation.utils import (
    compute_sha256,
    get_next_id,
    normalize_instruction_text,
    save_json,
)


def _get_group_key(text: Any) -> str:
    """Derive group key from normalized instruction text with NFKC."""
    norm = normalize_instruction_text(text, lowercase=True)
    if not norm:
        return ""
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


def split_dataset(
    cleaned_csv: Path | str,
    splits_dir: Path | str,
    report_dir: Path | str,
    split_version: str | None = None,
    run_id: str | None = None,
    test_size: float = 0.15,
    n_splits: int = 10,
    random_state: int = 42,
) -> dict[str, Any]:
    """Split cleaned dataset into hold-out test set and stratified group CV folds.

    Guarantees zero data leakage: identical or near-duplicate instructions stay in
    the exact same fold or partition.

    Args:
        cleaned_csv: Path to cleaned.csv.
        splits_dir: Base directory for storing splits.
        report_dir: Directory for storing split_report.json.
        split_version: Optional version string in DD-MM-YYYY-stt format.
        run_id: Optional run ID.
        test_size: Proportion of dataset for hold-out test set (e.g. 0.15).
        n_splits: Number of cross-validation folds for development set (default 10).
        random_state: Seed for reproducibility.

    Returns:
        Split summary report dictionary.
    """
    if test_size <= 0.0 or test_size >= 1.0:
        raise ValueError(f"test_size must be between 0.0 and 1.0, got {test_size}")

    clean_path = Path(cleaned_csv)
    if not clean_path.exists():
        raise FileNotFoundError(f"Cleaned dataset not found at {clean_path}")

    spl_base = Path(splits_dir)
    rep_dir = Path(report_dir)
    rep_dir.mkdir(parents=True, exist_ok=True)

    if split_version is None:
        split_version = get_next_id(spl_base)

    if run_id is None:
        run_id = split_version

    version_dir = spl_base / split_version
    version_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(clean_path)
    total_samples = len(df)
    clean_sha256 = compute_sha256(clean_path)

    if "sample_id" not in df.columns:
        raise ValueError("Missing 'sample_id' column in cleaned dataset")

    # Generate group IDs based on normalized instruction text
    df["_group_id"] = df["instruction"].apply(_get_group_key)
    y = df["intent"].values
    groups = df["_group_id"].values

    # Step 1: Split into Hold-out Test and Development Train
    n_test_folds = max(2, int(round(1.0 / test_size)))
    sgkf_test = StratifiedGroupKFold(n_splits=n_test_folds, shuffle=True, random_state=random_state)

    dev_indices: np.ndarray = np.array([])
    test_indices: np.ndarray = np.array([])

    for train_idx, val_idx in sgkf_test.split(df, y, groups):
        test_indices = val_idx
        dev_indices = train_idx
        break  # Use the first fold split as test

    df_dev = df.iloc[dev_indices].copy()
    df_test = df.iloc[test_indices].copy()

    # Step 2: Split Development Train into n_splits Folds
    sgkf_folds = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    y_dev = df_dev["intent"].values
    groups_dev = df_dev["_group_id"].values

    dev_fold_assignments = np.zeros(len(df_dev), dtype=int)
    for fold_num, (_, val_idx) in enumerate(sgkf_folds.split(df_dev, y_dev, groups_dev)):
        dev_fold_assignments[val_idx] = fold_num

    df_dev["fold"] = dev_fold_assignments
    df_dev["partition"] = "train"

    df_test["fold"] = -1
    df_test["partition"] = "test"

    # Combine back
    assignments = pd.concat([df_dev[["sample_id", "partition", "fold"]], df_test[["sample_id", "partition", "fold"]]], ignore_index=True)
    assignments = assignments.sort_values(by="sample_id").reset_index(drop=True)

    # Step 3: Zero-Leakage Verification Assertions
    merged = assignments.merge(df, on="sample_id")
    train_groups = set(merged[merged["partition"] == "train"]["_group_id"])
    test_groups = set(merged[merged["partition"] == "test"]["_group_id"])

    train_test_leak = train_groups.intersection(test_groups)
    if train_test_leak:
        raise ValueError(f"Data leakage detected! {len(train_test_leak)} groups overlap between train and test.")

    # Cross-fold leakage check
    train_df = merged[merged["partition"] == "train"]
    fold_leakages = {}
    folds = sorted(train_df["fold"].unique())
    for i in range(len(folds)):
        for j in range(i + 1, len(folds)):
            f1, f2 = folds[i], folds[j]
            g1 = set(train_df[train_df["fold"] == f1]["_group_id"])
            g2 = set(train_df[train_df["fold"] == f2]["_group_id"])
            overlap = g1.intersection(g2)
            if overlap:
                fold_leakages[f"{f1}_vs_{f2}"] = len(overlap)

    if fold_leakages:
        raise ValueError(f"Cross-fold leakage detected between folds: {fold_leakages}")

    # Step 4: Save split_assignments.csv
    assignments_csv_path = version_dir / "split_assignments.csv"
    assignments.to_csv(assignments_csv_path, index=False)

    # Step 5: Generate split_report.json
    class_dist_test = df_test["intent"].value_counts().to_dict()
    class_dist_train = df_dev["intent"].value_counts().to_dict()

    class_dist_per_fold: dict[str, dict[str, int]] = {}
    for f in folds:
        fold_samples = df_dev[df_dev["fold"] == f]
        class_dist_per_fold[f"fold_{f}"] = fold_samples["intent"].value_counts().to_dict()

    report = {
        "run_id": run_id,
        "split_version": split_version,
        "cleaned_file": str(clean_path),
        "cleaned_sha256": clean_sha256,
        "splits_sha256": compute_sha256(assignments_csv_path),
        "config": {
            "test_size": test_size,
            "n_splits": n_splits,
            "random_state": random_state,
        },
        "summary": {
            "total_samples": total_samples,
            "train_samples": len(df_dev),
            "test_samples": len(df_test),
            "unique_groups": int(df["_group_id"].nunique()),
            "leakage_detected": False,
        },
        "class_distribution": {
            "train": {k: int(v) for k, v in class_dist_train.items()},
            "test": {k: int(v) for k, v in class_dist_test.items()},
            "per_fold": {
                fold_name: {k: int(v) for k, v in dist.items()}
                for fold_name, dist in class_dist_per_fold.items()
            },
        },
        "artifacts": {
            "split_assignments": str(assignments_csv_path),
        },
    }

    save_json(report, rep_dir / "split_report.json")
    return report


def main() -> None:
    """CLI entrypoint for split_data."""
    parser = argparse.ArgumentParser(description="Split cleaned data into test and 10 CV folds with leakage prevention.")
    parser.add_argument("--input", required=True, help="Path to cleaned dataset CSV")
    parser.add_argument("--splits-dir", required=True, help="Base directory for splits")
    parser.add_argument("--report-dir", required=True, help="Directory to save split_report.json")
    parser.add_argument("--split-version", default=None, help="Version string in DD-MM-YYYY-stt format")
    parser.add_argument("--run-id", default=None, help="Run ID in DD-MM-YYYY-stt format")
    parser.add_argument("--test-size", type=float, default=0.15, help="Test set fraction (default: 0.15)")
    parser.add_argument("--n-splits", type=int, default=10, help="Number of folds (default: 10)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    result = split_dataset(
        cleaned_csv=args.input,
        splits_dir=args.splits_dir,
        report_dir=args.report_dir,
        split_version=args.split_version,
        run_id=args.run_id,
        test_size=args.test_size,
        n_splits=args.n_splits,
        random_state=args.seed,
    )
    print(f"Splitting complete for split_version: {result['split_version']}.")
    print(f"Train samples: {result['summary']['train_samples']}, Test samples: {result['summary']['test_samples']}")
    print("Leakage verification passed: 0% overlap.")


if __name__ == "__main__":
    main()
