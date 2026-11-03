"""End-to-end data preparation orchestrator for SupportIQ."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pipeline.preparation.clean_data import clean_dataset
from pipeline.preparation.features import build_and_save_train_features
from pipeline.preparation.inspect_data import inspect_dataset
from pipeline.preparation.split_data import split_dataset
from pipeline.preparation.utils import (
    compute_sha256,
    create_manifest,
    get_next_id,
    save_json,
)
from pipeline.preparation.validate_data import validate_dataset


def run_full_preparation(
    input_csv: Path | str,
    base_dir: Path | str | None = None,
    run_id: str | None = None,
    dataset_version: str | None = None,
    split_version: str | None = None,
    test_size: float = 0.15,
    n_splits: int = 10,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute end-to-end preparation pipeline: inspect -> validate -> clean -> split -> features.

    Args:
        input_csv: Path to raw dataset CSV.
        base_dir: Project root directory (default: current working directory).
        run_id: Run ID in DD-MM-YYYY-stt format. If None, auto-generated.
        dataset_version: Processed dataset version in DD-MM-YYYY-stt format.
        split_version: Split version in DD-MM-YYYY-stt format.
        test_size: Fraction of samples for hold-out test set (default: 0.15).
        n_splits: Number of cross-validation folds (default: 10).
        seed: Random seed for reproducibility.

    Returns:
        Execution summary dictionary with artifact locations.
    """
    root_path = Path(base_dir) if base_dir else Path.cwd()
    raw_input_path = Path(input_csv)
    if not raw_input_path.is_absolute():
        raw_input_path = root_path / raw_input_path

    if not raw_input_path.exists():
        raise FileNotFoundError(f"Raw dataset not found at {raw_input_path}")

    # Standard directory structure
    prep_artifacts_base = root_path / "artifacts" / "preparation"
    models_base = root_path / "artifacts" / "models"
    processed_base = root_path / "data" / "datasets" / "processed"
    splits_base = root_path / "data" / "datasets" / "splits"

    # Synchronize version IDs across artifacts and data directories
    if run_id is None:
        run_id = get_next_id(prep_artifacts_base)

    if dataset_version is None:
        dataset_version = run_id

    if split_version is None:
        split_version = run_id

    prep_dir = prep_artifacts_base / run_id
    prep_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Starting SupportIQ Data Preparation Pipeline [ID: {run_id}] ===")

    # 1. Inspect data & EDA
    print("[1/5] Running inspect_data and generating figures...")
    inspect_res = inspect_dataset(input_csv=raw_input_path, output_dir=prep_dir, run_id=run_id)

    # 2. Validate data
    print("[2/5] Running validate_data and conflict detection...")
    validate_res = validate_dataset(input_csv=raw_input_path, output_dir=prep_dir, run_id=run_id)

    # 3. Clean data & quarantine
    print(f"[3/5] Running clean_data for version {dataset_version}...")
    clean_res = clean_dataset(
        input_csv=raw_input_path,
        processed_dir=processed_base,
        report_dir=prep_dir,
        dataset_version=dataset_version,
        run_id=run_id,
    )
    cleaned_csv_path = Path(clean_res["artifacts"]["cleaned_csv"])

    # 4. Split data (Hold-out Test & 10-Fold CV with group leakage prevention)
    print(f"[4/5] Running split_data for split version {split_version}...")
    split_res = split_dataset(
        cleaned_csv=cleaned_csv_path,
        splits_dir=splits_base,
        report_dir=prep_dir,
        split_version=split_version,
        run_id=run_id,
        test_size=test_size,
        n_splits=n_splits,
        random_state=seed,
    )
    splits_csv_path = Path(split_res["artifacts"]["split_assignments"])

    # 5. Build and save TF-IDF feature transformer fit strictly on train partition
    print(f"[5/5] Fitting IntentFeaturePipeline on train partition...")
    model_path = build_and_save_train_features(
        cleaned_csv=cleaned_csv_path,
        splits_csv=splits_csv_path,
        output_dir=models_base,
        run_id=run_id,
    )

    # 6. Generate Lineage Manifest
    output_artifacts = {
        "profile": str(prep_dir / "profile.json"),
        "class_distribution": str(prep_dir / "class_distribution.csv"),
        "validation_report": str(prep_dir / "validation_report.json"),
        "review_candidates": str(prep_dir / "review_candidates.csv"),
        "duplicate_groups": str(prep_dir / "duplicate_groups.csv"),
        "cleaning_report": str(prep_dir / "cleaning_report.json"),
        "cleaned_csv": str(cleaned_csv_path),
        "quarantined_csv": str(clean_res["artifacts"]["quarantined_csv"]),
        "split_report": str(prep_dir / "split_report.json"),
        "split_assignments": str(splits_csv_path),
        "tfidf_model": str(model_path),
    }

    manifest = create_manifest(
        run_id=run_id,
        input_files={
            "raw_dataset": str(raw_input_path),
            "raw_sha256": compute_sha256(raw_input_path),
        },
        output_artifacts={k: str(v) for k, v in output_artifacts.items()},
        metadata={
            "dataset_version": dataset_version,
            "split_version": split_version,
            "raw_samples": inspect_res["total_samples"],
            "cleaned_samples": clean_res["final_clean_samples"],
            "quarantined_samples": clean_res["quarantined_samples"],
            "train_samples": split_res["summary"]["train_samples"],
            "test_samples": split_res["summary"]["test_samples"],
            "leakage_detected": split_res["summary"]["leakage_detected"],
        },
    )

    manifest_path = prep_dir / "manifest.json"
    save_json(manifest, manifest_path)

    print(f"=== Preparation Complete! Manifest saved to {manifest_path} ===")

    return {
        "run_id": run_id,
        "dataset_version": dataset_version,
        "split_version": split_version,
        "manifest_path": str(manifest_path),
        "artifacts": output_artifacts,
        "metadata": manifest["metadata"],
    }


def main() -> None:
    """CLI entrypoint for running the full preparation pipeline."""
    parser = argparse.ArgumentParser(description="Run complete data preparation pipeline for SupportIQ.")
    parser.add_argument("--input", required=True, help="Path to input raw CSV file")
    parser.add_argument("--run-id", default=None, help="Run ID in DD-MM-YYYY-stt format")
    parser.add_argument("--dataset-version", default=None, help="Processed dataset version in DD-MM-YYYY-stt format")
    parser.add_argument("--split-version", default=None, help="Split version in DD-MM-YYYY-stt format")
    parser.add_argument("--test-size", type=float, default=0.15, help="Test set fraction (default: 0.15)")
    parser.add_argument("--n-splits", type=int, default=10, help="Number of CV folds (default: 10)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    result = run_full_preparation(
        input_csv=args.input,
        run_id=args.run_id,
        dataset_version=args.dataset_version,
        split_version=args.split_version,
        test_size=args.test_size,
        n_splits=args.n_splits,
        seed=args.seed,
    )
    print(f"All artifacts successfully created for run {result['run_id']}.")


if __name__ == "__main__":
    main()
