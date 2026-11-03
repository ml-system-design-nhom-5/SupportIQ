# tests/unit/test_preparation.py
from pathlib import Path
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
