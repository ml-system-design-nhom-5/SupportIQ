"""Data cleaning and quarantine module for SupportIQ."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.preparation.utils import (
    STANDARD_INTENTS,
    compute_sha256,
    get_next_id,
    normalize_instruction_text,
    save_json,
)


def clean_text_instruction(text: Any) -> str:
    """Normalize text with NFKC, collapse multiple whitespaces, and strip edges."""
    return normalize_instruction_text(text, lowercase=False)


def clean_dataset(
    input_csv: Path | str,
    processed_dir: Path | str,
    report_dir: Path | str,
    dataset_version: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Clean dataset text, quarantine flawed samples, and deduplicate identical pairs.

    Args:
        input_csv: Path to raw dataset CSV file.
        processed_dir: Base directory for processed datasets.
        report_dir: Directory where cleaning report will be saved.
        dataset_version: Optional version string in DD-MM-YYYY-stt format.
        run_id: Optional run ID string.

    Returns:
        Cleaning summary dictionary.
    """
    input_path = Path(input_csv)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found at {input_path}")

    proc_base = Path(processed_dir)
    rep_dir = Path(report_dir)
    rep_dir.mkdir(parents=True, exist_ok=True)

    if dataset_version is None:
        dataset_version = get_next_id(proc_base)

    if run_id is None:
        run_id = dataset_version

    version_dir = proc_base / dataset_version
    version_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)
    total_raw_samples = len(df)
    raw_sha256 = compute_sha256(input_path)

    # Sanitize string columns
    if "intent" in df.columns:
        df["intent"] = df["intent"].fillna("").astype(str).str.strip()
    if "category" in df.columns:
        df["category"] = df["category"].fillna("").astype(str).str.strip()

    # Clean text column
    df["instruction_cleaned"] = df["instruction"].apply(clean_text_instruction)
    df["_orig_idx"] = range(total_raw_samples)

    quarantined_records: list[dict[str, Any]] = []
    quarantined_indices = set()

    # 1. Quarantine: missing required fields
    for idx, row in df.iterrows():
        inst = row["instruction_cleaned"]
        intent = row.get("intent")
        if not inst or pd.isna(intent) or str(intent).strip() == "":
            quarantined_indices.add(idx)
            row_dict = row.to_dict()
            row_dict["quarantine_reason"] = "missing_required_fields"
            quarantined_records.append(row_dict)

    # 2. Quarantine: invalid intent label
    for idx, row in df.iterrows():
        if idx in quarantined_indices:
            continue
        intent = str(row.get("intent")).strip()
        if intent not in STANDARD_INTENTS:
            quarantined_indices.add(idx)
            row_dict = row.to_dict()
            row_dict["quarantine_reason"] = "invalid_intent_label"
            quarantined_records.append(row_dict)

    # 3. Quarantine: conflicting duplicate groups
    # Group remaining valid candidates by lowercased cleaned instruction
    remaining_candidates = df[~df["_orig_idx"].isin(quarantined_indices)].copy()
    remaining_candidates["_norm_group"] = remaining_candidates["instruction_cleaned"].str.lower()

    grouped = remaining_candidates.groupby("_norm_group")
    for norm_group, group in grouped:
        unique_intents = group["intent"].unique()
        if len(unique_intents) > 1:
            for idx in group["_orig_idx"]:
                quarantined_indices.add(idx)
                row_dict = df.loc[idx].to_dict()
                row_dict["quarantine_reason"] = "conflicting_labels_across_duplicates"
                quarantined_records.append(row_dict)

    # 4. Clean subset & deduplication
    valid_df = df[~df["_orig_idx"].isin(quarantined_indices)].copy()
    initial_clean_count = len(valid_df)

    # Deduplicate exact pairs (instruction_cleaned + intent)
    valid_df["_dedup_key"] = valid_df["instruction_cleaned"].str.lower() + "|||" + valid_df["intent"].astype(str)
    deduped_df = valid_df.drop_duplicates(subset=["_dedup_key"], keep="first").copy()
    duplicates_removed_count = initial_clean_count - len(deduped_df)

    # Assign persistent sample_id
    deduped_df = deduped_df.reset_index(drop=True)
    deduped_df["sample_id"] = [f"sample_{i:06d}" for i in range(len(deduped_df))]
    deduped_df["instruction"] = deduped_df["instruction_cleaned"]

    # Select and reorder columns
    clean_columns = ["sample_id", "instruction", "intent", "category"]
    for extra_col in ["tags", "response"]:
        if extra_col in deduped_df.columns:
            clean_columns.append(extra_col)

    final_clean_df = deduped_df[clean_columns]
    cleaned_csv_path = version_dir / "cleaned.csv"
    final_clean_df.to_csv(cleaned_csv_path, index=False)

    # Save quarantined.csv with consistent schema
    original_cols = [c for c in df.columns if c not in ("instruction_cleaned", "_orig_idx")]
    df_quarantined = pd.DataFrame(quarantined_records)
    if df_quarantined.empty:
        df_quarantined = pd.DataFrame(columns=original_cols + ["quarantine_reason"])
    else:
        # Retain only original columns plus quarantine_reason
        for helper_col in ["instruction_cleaned", "_orig_idx"]:
            if helper_col in df_quarantined.columns:
                df_quarantined = df_quarantined.drop(columns=[helper_col])
        ordered_cols = [c for c in original_cols if c in df_quarantined.columns] + ["quarantine_reason"]
        df_quarantined = df_quarantined[ordered_cols]

    quarantined_csv_path = version_dir / "quarantined.csv"
    df_quarantined.to_csv(quarantined_csv_path, index=False)

    # Compute reasons breakdown
    reason_counts = (
        df_quarantined["quarantine_reason"].value_counts().to_dict()
        if not df_quarantined.empty
        else {}
    )

    report = {
        "run_id": run_id,
        "dataset_version": dataset_version,
        "input_file": str(input_path),
        "raw_sha256": raw_sha256,
        "cleaned_sha256": compute_sha256(cleaned_csv_path),
        "total_raw_samples": total_raw_samples,
        "quarantined_samples": len(df_quarantined),
        "quarantine_reasons": {k: int(v) for k, v in reason_counts.items()},
        "exact_duplicates_removed": duplicates_removed_count,
        "final_clean_samples": len(final_clean_df),
        "artifacts": {
            "cleaned_csv": str(cleaned_csv_path),
            "quarantined_csv": str(quarantined_csv_path),
        },
    }

    save_json(report, rep_dir / "cleaning_report.json")
    return report


def main() -> None:
    """CLI entrypoint for clean_data."""
    parser = argparse.ArgumentParser(description="Clean dataset text, deduplicate, and quarantine flawed samples.")
    parser.add_argument("--input", required=True, help="Path to input raw CSV file")
    parser.add_argument("--processed-dir", required=True, help="Base directory for processed outputs")
    parser.add_argument("--report-dir", required=True, help="Directory to save cleaning_report.json")
    parser.add_argument("--dataset-version", default=None, help="Version string in DD-MM-YYYY-stt format")
    parser.add_argument("--run-id", default=None, help="Run ID in DD-MM-YYYY-stt format")
    args = parser.parse_args()

    result = clean_dataset(
        input_csv=args.input,
        processed_dir=args.processed_dir,
        report_dir=args.report_dir,
        dataset_version=args.dataset_version,
        run_id=args.run_id,
    )
    print(f"Cleaning complete for version: {result['dataset_version']}.")
    print(f"Clean samples: {result['final_clean_samples']}, Quarantined: {result['quarantined_samples']}")


if __name__ == "__main__":
    main()
