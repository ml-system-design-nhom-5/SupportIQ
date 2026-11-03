# tests/unit/test_preparation.py
from pathlib import Path
import pandas as pd
import pytest

def test_data_science_packages_installed():
    import pandas as pd
    import numpy as np
    import sklearn
    import joblib
    import matplotlib
    assert pd.__version__ is not None
    assert np.__version__ is not None
    assert sklearn.__version__ is not None
    assert joblib.__version__ is not None
    assert matplotlib.__version__ is not None

def test_id_generation_formatting_and_auto_increment(tmp_path: Path):
    from pipeline.preparation.utils import get_next_id

    fixed_date = "03-11-2026"
    # Empty dir should start with 00
    id_0 = get_next_id(tmp_path, date_str=fixed_date)
    assert id_0 == "03-11-2026-00"

    # Simulate existing folders
    (tmp_path / "03-11-2026-00").mkdir()
    (tmp_path / "03-11-2026-01").mkdir()
    (tmp_path / "other-dir").mkdir()

    id_next = get_next_id(tmp_path, date_str=fixed_date)
    assert id_next == "03-11-2026-02"

def test_sha256_and_json_io(tmp_path: Path):
    from pipeline.preparation.utils import compute_sha256, save_json, load_json

    test_file = tmp_path / "sample.txt"
    test_file.write_text("supportiq", encoding="utf-8")
    sha = compute_sha256(test_file)
    assert len(sha) == 64
    assert sha.isupper()

    json_file = tmp_path / "data.json"
    data = {"run_id": "03-11-2026-00", "count": 42}
    save_json(data, json_file)
    loaded = load_json(json_file)
    assert loaded == data

def test_constants_count():
    from pipeline.preparation.utils import STANDARD_INTENTS, STANDARD_CATEGORIES
    assert len(STANDARD_INTENTS) == 46
    assert len(STANDARD_CATEGORIES) == 13

def test_inspect_dataset_creates_expected_artifacts(tmp_path: Path):
    from pipeline.preparation.inspect_data import inspect_dataset

    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({
        "instruction": ["How to track order?", "Cancel my order please", "Check refund status"],
        "intent": ["track_order", "cancel_order", "refund_status"],
        "category": ["ORDER", "ORDER", "RETURNS"],
        "tags": ["order", "cancel", "refund"],
        "response": ["resp1", "resp2", "resp3"]
    })
    df.to_csv(csv_path, index=False)

    artifacts_dir = tmp_path / "artifacts"
    result = inspect_dataset(csv_path, artifacts_dir, run_id="03-11-2026-00")

    assert result["run_id"] == "03-11-2026-00"
    assert result["total_samples"] == 3
    assert (artifacts_dir / "profile.json").exists()
    assert (artifacts_dir / "class_distribution.csv").exists()
    assert (artifacts_dir / "figures" / "class_distribution.png").exists()
    assert (artifacts_dir / "figures" / "length_distribution.png").exists()
    assert (artifacts_dir / "figures" / "category_intent_matrix.png").exists()

def test_validate_dataset_detects_errors_and_duplicates(tmp_path: Path):
    from pipeline.preparation.validate_data import validate_dataset

    csv_path = tmp_path / "dirty.csv"
    df = pd.DataFrame({
        "instruction": [
            "Valid question?",
            "",  # empty string
            "Where is order?",
            "Where is order?",  # exact duplicate same intent
            "Cancel my order",
            "cancel my order ", # normalized duplicate conflicting intent!
            "Unknown intent query"
        ],
        "intent": [
            "track_order",
            "track_order",
            "track_order",
            "track_order",
            "cancel_order",
            "track_order",      # conflict!
            "non_existent_intent"
        ],
        "category": [
            "ORDER",
            "ORDER",
            "ORDER",
            "ORDER",
            "ORDER",
            "ORDER",
            "UNKNOWN_CAT"
        ]
    })
    df.to_csv(csv_path, index=False)

    artifacts_dir = tmp_path / "artifacts"
    report = validate_dataset(csv_path, artifacts_dir, run_id="03-11-2026-00")

    assert report["summary"]["total_records"] == 7
    assert report["summary"]["missing_instruction"] == 1
    assert report["summary"]["invalid_intents"] == 1
    assert report["summary"]["conflicting_duplicates"] >= 1

    assert (artifacts_dir / "validation_report.json").exists()
    assert (artifacts_dir / "review_candidates.csv").exists()
    assert (artifacts_dir / "duplicate_groups.csv").exists()

def test_clean_dataset_quarantines_and_cleans(tmp_path: Path):
    from pipeline.preparation.clean_data import clean_dataset

    csv_path = tmp_path / "raw.csv"
    df = pd.DataFrame({
        "instruction": [
            "  Please track {{Tracking Number}}!  ",
            "Please track {{Tracking Number}}!", # exact duplicate
            "Cancel order {{Order History}}",
            "cancel order {{order history}}",   # conflict if different intent
            "  ",                               # empty
            "Valid inquiry with unknown intent"
        ],
        "intent": [
            "track_order",
            "track_order",
            "cancel_order",
            "refund_status",                    # conflict!
            "track_order",
            "unknown_intent"
        ],
        "category": ["ORDER", "ORDER", "ORDER", "RETURNS", "ORDER", "MISC"]
    })
    df.to_csv(csv_path, index=False)

    processed_dir = tmp_path / "processed"
    report_dir = tmp_path / "artifacts"
    res = clean_dataset(csv_path, processed_dir, report_dir, dataset_version="03-11-2026-00", run_id="03-11-2026-00")

    cleaned_csv = processed_dir / "03-11-2026-00" / "cleaned.csv"
    quarantined_csv = processed_dir / "03-11-2026-00" / "quarantined.csv"
    report_json = report_dir / "cleaning_report.json"

    assert cleaned_csv.exists()
    assert quarantined_csv.exists()
    assert report_json.exists()

    df_cleaned = pd.read_csv(cleaned_csv)
    df_quarantined = pd.read_csv(quarantined_csv)

    # Cleaned should have 1 row: "Please track {{Tracking Number}}!" (deduplicated)
    assert len(df_cleaned) == 1
    assert "sample_id" in df_cleaned.columns
    assert df_cleaned.iloc[0]["instruction"] == "Please track {{Tracking Number}}!"

    # Quarantined should contain the conflicting pair, empty row, and unknown intent
    assert len(df_quarantined) == 4
    assert set(df_quarantined["quarantine_reason"]).issuperset({
        "conflicting_labels_across_duplicates",
        "missing_required_fields",
        "invalid_intent_label"
    })

def test_split_dataset_stratified_no_leakage(tmp_path: Path):
    from pipeline.preparation.split_data import split_dataset

    cleaned_csv = tmp_path / "cleaned.csv"
    records = []
    for i in range(25):
        records.append({
            "sample_id": f"s_a_{i}",
            "instruction": f"Query type A variant {i % 5}",
            "intent": "track_order",
            "category": "ORDER"
        })
        records.append({
            "sample_id": f"s_b_{i}",
            "instruction": f"Query type B variant {i % 5}",
            "intent": "cancel_order",
            "category": "ORDER"
        })
    df = pd.DataFrame(records)
    df.to_csv(cleaned_csv, index=False)

    splits_dir = tmp_path / "splits"
    report_dir = tmp_path / "artifacts"

    res = split_dataset(
        cleaned_csv=cleaned_csv,
        splits_dir=splits_dir,
        report_dir=report_dir,
        split_version="03-11-2026-00",
        run_id="03-11-2026-00",
        test_size=0.2,
        n_splits=3,
        random_state=42
    )

    assignments_csv = splits_dir / "03-11-2026-00" / "split_assignments.csv"
    report_json = report_dir / "split_report.json"

    assert assignments_csv.exists()
    assert report_json.exists()

    df_assign = pd.read_csv(assignments_csv)
    assert len(df_assign) == 50
    assert set(df_assign["partition"]) == {"train", "test"}

    # Merge with original data to verify group leakage
    merged = df_assign.merge(df, on="sample_id")
    train_texts = set(merged[merged["partition"] == "train"]["instruction"])
    test_texts = set(merged[merged["partition"] == "test"]["instruction"])

    # NO LEAKAGE: Intersection of texts between train and test must be empty!
    assert len(train_texts.intersection(test_texts)) == 0

    # Cross-fold leakage check for train partition
    train_df = merged[merged["partition"] == "train"]
    folds = train_df["fold"].unique()
    for f1 in folds:
        for f2 in folds:
            if f1 != f2:
                texts_f1 = set(train_df[train_df["fold"] == f1]["instruction"])
                texts_f2 = set(train_df[train_df["fold"] == f2]["instruction"])
                assert len(texts_f1.intersection(texts_f2)) == 0
