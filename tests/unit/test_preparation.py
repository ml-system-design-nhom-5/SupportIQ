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
