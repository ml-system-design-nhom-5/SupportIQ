"""Data validation and consistency verification module."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.preparation.utils import (
    STANDARD_CATEGORIES,
    STANDARD_INTENTS,
    compute_sha256,
    get_next_id,
    save_json,
)


def normalize_text_for_dedup(text: Any) -> str:
    """Normalize text by stripping, lowercasing, and collapsing whitespace."""
    if pd.isna(text):
        return ""
    text_str = str(text).strip().lower()
    return re.sub(r"\s+", " ", text_str)


def validate_dataset(
    input_csv: Path | str,
    output_dir: Path | str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Validate schema, missing values, valid taxonomy, and duplicate conflicts.

    Args:
        input_csv: Path to dataset CSV file.
        output_dir: Path to directory where validation artifacts are stored.
        run_id: Optional run ID.

    Returns:
        Validation report dictionary.
    """
    input_path = Path(input_csv)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found at {input_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if run_id is None:
        run_id = get_next_id(out_dir)

    df = pd.read_csv(input_path)
    total_records = len(df)
    file_sha256 = compute_sha256(input_path)

    # 1. Schema check
    required_cols = ["instruction", "intent", "category"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Schema violation: missing required columns {missing_cols}")

    # Track issue reasons per record
    issue_reasons: list[list[str]] = [[] for _ in range(total_records)]

    # 2. Completeness check
    missing_instruction_mask = df["instruction"].isna() | (df["instruction"].astype(str).str.strip() == "")
    missing_intent_mask = df["intent"].isna() | (df["intent"].astype(str).str.strip() == "")

    for idx, is_missing in enumerate(missing_instruction_mask):
        if is_missing:
            issue_reasons[idx].append("missing_instruction")

    for idx, is_missing in enumerate(missing_intent_mask):
        if is_missing:
            issue_reasons[idx].append("missing_intent")

    # 3. Validity check (Taxonomy)
    valid_intents_mask = df["intent"].isin(STANDARD_INTENTS)
    invalid_intents_mask = ~valid_intents_mask & ~missing_intent_mask

    for idx, is_invalid in enumerate(invalid_intents_mask):
        if is_invalid:
            issue_reasons[idx].append("invalid_intent")

    valid_cats_mask = df["category"].isin(STANDARD_CATEGORIES)
    invalid_cats_mask = ~valid_cats_mask & df["category"].notna()

    for idx, is_invalid in enumerate(invalid_cats_mask):
        if is_invalid:
            issue_reasons[idx].append("invalid_category")

    # 4. Duplicate & Conflict Check
    df_eval = df.copy()
    df_eval["_orig_idx"] = range(total_records)
    df_eval["_norm_text"] = df_eval["instruction"].apply(normalize_text_for_dedup)

    # Group by non-empty normalized instruction
    valid_text_mask = df_eval["_norm_text"] != ""
    groups = df_eval[valid_text_mask].groupby("_norm_text")

    duplicate_rows: list[dict[str, Any]] = []
    duplicate_groups_count = 0
    conflicting_groups_count = 0
    conflicting_records_count = 0

    for norm_text, group in groups:
        if len(group) > 1:
            duplicate_groups_count += 1
            group_id = f"group_{hashlib.md5(norm_text.encode('utf-8')).hexdigest()[:8]}"
            intents_in_group = group["intent"].dropna().unique()
            is_conflicting = len(intents_in_group) > 1

            if is_conflicting:
                conflicting_groups_count += 1
                conflicting_records_count += len(group)

            for _, row in group.iterrows():
                orig_idx = int(row["_orig_idx"])
                if is_conflicting:
                    issue_reasons[orig_idx].append("conflicting_labels_across_duplicates")
                else:
                    issue_reasons[orig_idx].append("exact_duplicate")

                duplicate_rows.append({
                    "duplicate_group_id": group_id,
                    "original_index": orig_idx,
                    "instruction": row["instruction"],
                    "intent": row["intent"],
                    "category": row["category"],
                    "is_conflicting": is_conflicting,
                })

    # 5. Output duplicate_groups.csv
    df_duplicates = pd.DataFrame(duplicate_rows)
    if df_duplicates.empty:
        df_duplicates = pd.DataFrame(columns=[
            "duplicate_group_id", "original_index", "instruction", "intent", "category", "is_conflicting"
        ])
    df_duplicates.to_csv(out_dir / "duplicate_groups.csv", index=False)

    # 6. Output review_candidates.csv
    review_rows: list[dict[str, Any]] = []
    for idx, reasons in enumerate(issue_reasons):
        if reasons:
            row_dict = df.iloc[idx].to_dict()
            row_dict["original_index"] = idx
            row_dict["issue_reasons"] = ";".join(reasons)
            review_rows.append(row_dict)

    df_review = pd.DataFrame(review_rows)
    if df_review.empty:
        df_review = pd.DataFrame(columns=list(df.columns) + ["original_index", "issue_reasons"])
    df_review.to_csv(out_dir / "review_candidates.csv", index=False)

    # 7. Summary report
    total_flagged = len(df_review)
    report = {
        "run_id": run_id,
        "input_file": str(input_path),
        "sha256": file_sha256,
        "summary": {
            "total_records": total_records,
            "valid_records": total_records - total_flagged,
            "missing_instruction": int(missing_instruction_mask.sum()),
            "missing_intent": int(missing_intent_mask.sum()),
            "invalid_intents": int(invalid_intents_mask.sum()),
            "invalid_categories": int(invalid_cats_mask.sum()),
            "total_duplicate_groups": duplicate_groups_count,
            "conflicting_duplicate_groups": conflicting_groups_count,
            "conflicting_duplicates": conflicting_records_count,
            "review_candidates_count": total_flagged,
            "validation_passed": total_flagged == 0,
        },
        "artifacts": {
            "validation_report": "validation_report.json",
            "review_candidates": "review_candidates.csv",
            "duplicate_groups": "duplicate_groups.csv",
        },
    }

    save_json(report, out_dir / "validation_report.json")
    return report


def main() -> None:
    """CLI entrypoint for validate_data."""
    parser = argparse.ArgumentParser(description="Validate dataset quality, taxonomy, and duplicate conflicts.")
    parser.add_argument("--input", required=True, help="Path to input CSV file")
    parser.add_argument("--output-dir", required=True, help="Directory to save validation artifacts")
    parser.add_argument("--run-id", default=None, help="Run ID in DD-MM-YYYY-stt format")
    args = parser.parse_args()

    result = validate_dataset(input_csv=args.input, output_dir=args.output_dir, run_id=args.run_id)
    summary = result["summary"]
    print(f"Validation complete for run_id: {result['run_id']}.")
    print(f"Total: {summary['total_records']}, Flagged review candidates: {summary['review_candidates_count']}")


if __name__ == "__main__":
    main()
