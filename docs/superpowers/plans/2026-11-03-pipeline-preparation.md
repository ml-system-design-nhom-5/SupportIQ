# Data Preparation & Features Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete `pipeline/preparation/` subsystem for SupportIQ, implementing data profiling, validation, cleaning, leakage-free 10-fold stratified group splitting, and TF-IDF feature extraction with synchronized `<ngày>-<tháng>-<năm>-<stt>` ID generation and comprehensive artifact manifests.

**Architecture:** A modular Python pipeline consisting of 5 dedicated single-responsibility scripts, shared utilities (`utils.py`), and an orchestrator (`run_preparation.py`). Every script supports both standalone CLI execution and programmatic import, and enforces data contracts (DQ-01 to DQ-04) with strict hold-out test isolation and no-leakage verification.

**Tech Stack:** Python 3.12, pandas, numpy, scikit-learn, joblib, matplotlib, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-pipeline-preparation-design.md`

## Global Constraints

- Python version: `>=3.12`.
- Virtual environment: `.venv` at project root.
- All generated run IDs, dataset versions, and split versions MUST follow `<ngày>-<tháng>-<năm>-<stt>` (e.g. `03-11-2026-00`).
- Raw data at `data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv` must NEVER be modified or overwritten.
- Standard 46 intents and 13 categories must match the Bitext dataset taxonomy verbatim.
- Entity placeholders `{{...}}` must be preserved in text preprocessing and feature extraction token patterns.
- TF-IDF feature transformers must NEVER be fit on the entire dataset; only on train folds/partitions.
- Zero data leakage: samples in the same duplicate or near-duplicate group must belong to the exact same fold or partition.

## Review Focus

1. **Date format zero-padding:** Ensure single-digit days or months (e.g., day 3, month 11) produce `03-11-2026-00` and not `3-11-2026-00` or `03-11-2026-0`.
2. **Conflicting duplicate labels:** When the exact same normalized `instruction` appears with two different `intent` labels, both samples must be quarantined to prevent label noise from corrupting training or evaluation.
3. **Regex token pattern with curly braces:** `TfidfVectorizer` default token pattern `(?u)\b\w\w+\b` drops `{` and `}`, splitting `{{Order History}}` into `Order` and `History`. The custom pattern must treat `{{...}}` as a single indivisible token.
4. **Group leakage across folds:** When grouping identical or near-duplicate questions, `StratifiedGroupKFold` must ensure no group spans both Train and Test or multiple folds, verified by an automated hash set assertion.
5. **Headless matplotlib environments:** Generating EDA figures on servers or Windows CLI must use `matplotlib.use('Agg')` before importing `pyplot` to prevent GUI backend crashes.

---

### Task 1: Environment & Dependencies Setup

**Files:**
- Create: `pipeline/requirements.txt`
- Modify: `.gitignore`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: None
- Produces: Installed dependencies (`pandas`, `numpy`, `scikit-learn`, `joblib`, `matplotlib`) in `.venv`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_preparation.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_data_science_packages_installed -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pandas'`

- [ ] **Step 3: Create `pipeline/requirements.txt` and install dependencies**

Create `pipeline/requirements.txt` containing:
```text
pandas>=2.2.0
numpy>=1.26.0
scikit-learn>=1.5.0
joblib>=1.4.0
matplotlib>=3.9.0
```
Run `.\.venv\Scripts\pip install -r pipeline/requirements.txt` to install into `.venv`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_data_science_packages_installed -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/requirements.txt tests/unit/test_preparation.py
git commit -m "chore(pipeline): add data science dependencies and verification test"
```

---

### Task 2: Shared Utilities & ID Management (`utils.py`)

**Files:**
- Create: `pipeline/preparation/__init__.py`
- Create: `pipeline/preparation/utils.py`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: None
- Produces:
  - `get_next_id(base_dir: Path | str, date_str: str | None = None) -> str`
  - `compute_sha256(file_path: Path | str) -> str`
  - `save_json(data: dict, file_path: Path | str) -> Path`
  - `load_json(file_path: Path | str) -> dict`
  - `create_manifest(run_id: str, input_files: dict[str, str], output_artifacts: dict[str, str], metadata: dict) -> dict`
  - Standard constants: `STANDARD_INTENTS` (set of 46), `STANDARD_CATEGORIES` (set of 13).

- [ ] **Step 1: Write the failing tests**

```python
# In tests/unit/test_preparation.py
from pathlib import Path
from pipeline.preparation.utils import (
    get_next_id,
    compute_sha256,
    save_json,
    load_json,
    STANDARD_INTENTS,
    STANDARD_CATEGORIES,
)

def test_id_generation_formatting_and_auto_increment(tmp_path: Path):
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
    assert len(STANDARD_INTENTS) == 46
    assert len(STANDARD_CATEGORIES) == 13
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k "test_id_generation or test_sha256 or test_constants" -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.preparation.utils'`

- [ ] **Step 3: Implement `pipeline/preparation/__init__.py` and `pipeline/preparation/utils.py`**

- `get_next_id`: Regex match `r"^(\d{2})-(\d{2})-(\d{4})-(\d{2})$"` filtered by today's date (or `date_str`). Format: `f"{day:02d}-{month:02d}-{year:04d}-{next_seq:02d}"`.
- `compute_sha256`: Read in 64KB chunks via `hashlib.sha256().hexdigest().upper()`.
- `save_json` / `load_json`: Atomic/clean write with `indent=2, ensure_ascii=False`.
- `STANDARD_INTENTS` and `STANDARD_CATEGORIES`: All 46 intents and 13 categories extracted from Bitext README.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k "test_id_generation or test_sha256 or test_constants" -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/preparation/__init__.py pipeline/preparation/utils.py tests/unit/test_preparation.py
git commit -m "feat(pipeline): add shared utils, ID generator, and Bitext taxonomy constants"
```

---

### Task 3: Data Inspection & EDA (`inspect_data.py`)

**Files:**
- Create: `pipeline/preparation/inspect_data.py`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: `pipeline.preparation.utils` (`get_next_id`, `compute_sha256`, `save_json`)
- Produces:
  - `inspect_dataset(input_csv: Path | str, output_dir: Path | str, run_id: str | None = None) -> dict`
  - CLI: `python -m pipeline.preparation.inspect_data --input <csv> --output-dir <dir> [--run-id <id>]`
  - Artifacts: `profile.json`, `class_distribution.csv`, `figures/class_distribution.png`, `figures/length_distribution.png`, `figures/category_intent_matrix.png`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/unit/test_preparation.py
import pandas as pd
from pipeline.preparation.inspect_data import inspect_dataset

def test_inspect_dataset_creates_expected_artifacts(tmp_path: Path):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_inspect_dataset_creates_expected_artifacts -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.preparation.inspect_data'`

- [ ] **Step 3: Implement `pipeline/preparation/inspect_data.py`**

- Use `matplotlib.use('Agg')` before importing `pyplot`.
- Compute dataset statistics: total rows, null counts, unique intents, unique categories.
- Length profiling: character counts and token counts (via `.split()`), calculate `min`, `max`, `mean`, `median`, `p90`, `p95`, `p99`.
- Plotting:
  - `class_distribution.png`: horizontal bar chart of top/all intents.
  - `length_distribution.png`: histogram of token counts.
  - `category_intent_matrix.png`: cross-tabulation heatmap between category and intent.
- CLI argument parsing via `argparse`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_inspect_dataset_creates_expected_artifacts -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/preparation/inspect_data.py tests/unit/test_preparation.py
git commit -m "feat(pipeline): add data inspection and EDA visualization module"
```

---

### Task 4: Data Validation (`validate_data.py`)

**Files:**
- Create: `pipeline/preparation/validate_data.py`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: `pipeline.preparation.utils` (`STANDARD_INTENTS`, `STANDARD_CATEGORIES`, `save_json`)
- Produces:
  - `validate_dataset(input_csv: Path | str, output_dir: Path | str, run_id: str | None = None) -> dict`
  - CLI: `python -m pipeline.preparation.validate_data --input <csv> --output-dir <dir> [--run-id <id>]`
  - Artifacts: `validation_report.json`, `review_candidates.csv`, `duplicate_groups.csv`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/unit/test_preparation.py
from pipeline.preparation.validate_data import validate_dataset

def test_validate_dataset_detects_errors_and_duplicates(tmp_path: Path):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_validate_dataset_detects_errors_and_duplicates -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.preparation.validate_data'`

- [ ] **Step 3: Implement `pipeline/preparation/validate_data.py`**

- Schema validation: check presence of `instruction`, `intent`, `category`.
- Check missing: null, whitespace-only.
- Check valid values: `intent in STANDARD_INTENTS`, `category in STANDARD_CATEGORIES`.
- Check duplicates and conflicts:
  - Normalize text: lowercase, strip leading/trailing spaces, collapse multiple spaces.
  - Group by normalized text:
    - If `intent.nunique() > 1`: mark as `conflicting_labels_across_duplicates`.
    - If `len(group) > 1` and `intent.nunique() == 1`: mark as `exact_duplicates`.
- Assign `duplicate_group_id` for groups with size > 1.
- Output `validation_report.json`, `review_candidates.csv` (rows with any issue flagged), and `duplicate_groups.csv`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_validate_dataset_detects_errors_and_duplicates -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/preparation/validate_data.py tests/unit/test_preparation.py
git commit -m "feat(pipeline): add data validation and duplicate conflict detection module"
```

---

### Task 5: Data Cleaning & Quarantine (`clean_data.py`)

**Files:**
- Create: `pipeline/preparation/clean_data.py`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: `pipeline.preparation.utils` (`STANDARD_INTENTS`, `save_json`)
- Produces:
  - `clean_dataset(input_csv: Path | str, processed_dir: Path | str, report_dir: Path | str, dataset_version: str | None = None, run_id: str | None = None) -> dict`
  - CLI: `python -m pipeline.preparation.clean_data --input <csv> --processed-dir <dir> --report-dir <dir> [--dataset-version <v>] [--run-id <id>]`
  - Output files:
    - `data/datasets/processed/<dataset-version>/cleaned.csv`
    - `data/datasets/processed/<dataset-version>/quarantined.csv`
    - `artifacts/preparation/<run-id>/cleaning_report.json`

- [ ] **Step 1: Write the failing test**

```python
# In tests/unit/test_preparation.py
from pipeline.preparation.clean_data import clean_dataset

def test_clean_dataset_quarantines_and_cleans(tmp_path: Path):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_clean_dataset_quarantines_and_cleans -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.preparation.clean_data'`

- [ ] **Step 3: Implement `pipeline/preparation/clean_data.py`**

- Text normalization: `unicodedata.normalize('NFKC', text)`, regex whitespace collapse `\s+` to `' '`, strip.
- Quarantine:
  - Empty or null `instruction`/`intent` -> `missing_required_fields`.
  - Intent not in `STANDARD_INTENTS` -> `invalid_intent_label`.
  - Normalized instructions with multiple unique intents -> quarantine ALL rows of that group with `conflicting_labels_across_duplicates`.
- Deduplication: for remaining valid rows, drop duplicates based on normalized instruction and intent, preserving the first.
- Assign `sample_id` as `sample_{index:06d}`.
- Save `cleaned.csv`, `quarantined.csv`, and `cleaning_report.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_clean_dataset_quarantines_and_cleans -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/preparation/clean_data.py tests/unit/test_preparation.py
git commit -m "feat(pipeline): add data cleaning and quarantine module"
```

---

### Task 6: Data Partitioning & Leakage Prevention (`split_data.py`)

**Files:**
- Create: `pipeline/preparation/split_data.py`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: `pipeline.preparation.utils` (`save_json`)
- Produces:
  - `split_dataset(cleaned_csv: Path | str, splits_dir: Path | str, report_dir: Path | str, split_version: str | None = None, run_id: str | None = None, test_size: float = 0.15, n_splits: int = 10, random_state: int = 42) -> dict`
  - CLI: `python -m pipeline.preparation.split_data --input <cleaned_csv> --splits-dir <dir> --report-dir <dir> [--split-version <v>] [--run-id <id>]`
  - Output files:
    - `data/datasets/splits/<split-version>/split_assignments.csv`
    - `artifacts/preparation/<run-id>/split_report.json`

- [ ] **Step 1: Write the failing test**

```python
# In tests/unit/test_preparation.py
from pipeline.preparation.split_data import split_dataset

def test_split_dataset_stratified_no_leakage(tmp_path: Path):
    cleaned_csv = tmp_path / "cleaned.csv"
    # Create 50 samples across 2 intents, with some duplicate text groups
    records = []
    for i in range(25):
        records.append({
            "sample_id": f"s_a_{i}",
            "instruction": f"Query type A variant {i % 5}",  # Repeated text creates groups
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_split_dataset_stratified_no_leakage -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.preparation.split_data'`

- [ ] **Step 3: Implement `pipeline/preparation/split_data.py`**

- Form semantic groups: hash or lowercase normalized `instruction` as group ID.
- Partition Test set using `StratifiedGroupKFold(n_splits=round(1/test_size))` or group-aware stratified sampling.
- Partition remaining Development set into 10 folds using `StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=random_state)`.
- Enforce automated assertion: verify that `set(train_groups) & set(test_groups) == set()` and cross-fold intersections are empty.
- Generate `split_assignments.csv` (`sample_id`, `partition`, `fold`).
- Generate `split_report.json` with partition counts, class distributions per fold, and leakage verification status (`leakage_detected: False`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_split_dataset_stratified_no_leakage -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/preparation/split_data.py tests/unit/test_preparation.py
git commit -m "feat(pipeline): add stratified group splitting module with automated leakage prevention"
```

---

### Task 7: TF-IDF Feature Transformer (`features.py`)

**Files:**
- Create: `pipeline/preparation/features.py`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: None (pure transformer)
- Produces:
  - Class `IntentFeaturePipeline`:
    - `fit(texts: Iterable[str]) -> IntentFeaturePipeline`
    - `transform(texts: Iterable[str]) -> scipy.sparse.csr_matrix`
    - `fit_transform(texts: Iterable[str]) -> scipy.sparse.csr_matrix`
    - `save(path: str | Path) -> None`
    - `load(path: str | Path) -> IntentFeaturePipeline`
  - CLI: `python -m pipeline.preparation.features --cleaned-csv <csv> --splits-csv <csv> --output-dir <dir> [--run-id <id>]`
  - Artifacts: `artifacts/models/<run-id>/tfidf.joblib`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/unit/test_preparation.py
from pipeline.preparation.features import IntentFeaturePipeline

def test_intent_feature_pipeline_preserves_placeholders_and_persists(tmp_path: Path):
    texts = [
        "Track my package with {{Tracking Number}} please",
        "View {{Order History}} and cancel order",
        "Check refund status"
    ]
    pipeline = IntentFeaturePipeline(max_features=50, ngram_range=(1, 2))
    matrix = pipeline.fit_transform(texts)
    assert matrix.shape[0] == 3

    # Ensure placeholder was kept as a feature token
    vocab = pipeline.get_feature_names()
    assert any("{{tracking number}}" in term.lower() for term in vocab)

    # Test persistence with joblib
    model_path = tmp_path / "tfidf.joblib"
    pipeline.save(model_path)
    assert model_path.exists()

    loaded_pipeline = IntentFeaturePipeline.load(model_path)
    test_matrix = loaded_pipeline.transform(["Where is {{Tracking Number}}?"])
    assert test_matrix.shape[1] == matrix.shape[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_intent_feature_pipeline_preserves_placeholders_and_persists -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.preparation.features'`

- [ ] **Step 3: Implement `pipeline/preparation/features.py`**

- Wrap `TfidfVectorizer` with:
  - `token_pattern=r"(?u)\b\w+\b|\{\{[^}]+\}\}"`
  - `ngram_range=(1, 2)`
  - `sublinear_tf=True`
  - `min_df=2`
  - `max_features=10000`
- Implement `fit`, `transform`, `fit_transform`, `save` (via `joblib.dump`), and `load` (via `joblib.load`).
- Implement CLI tool allowing test-fitting on the train partition from `split_assignments.csv` and saving `tfidf.joblib`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_intent_feature_pipeline_preserves_placeholders_and_persists -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/preparation/features.py tests/unit/test_preparation.py
git commit -m "feat(pipeline): add TF-IDF feature pipeline with placeholder preservation and serialization"
```

---

### Task 8: End-to-End Orchestrator (`run_preparation.py`) & Full Pipeline Integration Test

**Files:**
- Create: `pipeline/preparation/run_preparation.py`
- Test: `tests/unit/test_preparation.py`

**Interfaces:**
- Consumes: All modules from Tasks 2-7
- Produces:
  - `run_full_preparation(input_csv: Path | str, run_id: str | None = None, dataset_version: str | None = None, split_version: str | None = None) -> dict`
  - CLI: `python -m pipeline.preparation.run_preparation --input <csv> [--run-id <id>]`
  - Manifest: `artifacts/preparation/<run-id>/manifest.json`

- [ ] **Step 1: Write the failing integration test**

```python
# In tests/unit/test_preparation.py
from pipeline.preparation.run_preparation import run_full_preparation

def test_run_full_preparation_synthetic_end_to_end(tmp_path: Path):
    raw_csv = tmp_path / "raw.csv"
    records = []
    # Generate 50 valid records across 2 standard intents
    for i in range(25):
        records.append({
            "instruction": f"I want to track order {{Order History}} number {i}",
            "intent": "track_order",
            "category": "ORDER",
            "tags": "order,track",
            "response": "Response"
        })
        records.append({
            "instruction": f"Please cancel order {{Order History}} number {i}",
            "intent": "cancel_order",
            "category": "ORDER",
            "tags": "order,cancel",
            "response": "Response"
        })
    pd.DataFrame(records).to_csv(raw_csv, index=False)

    base_dir = tmp_path
    result = run_full_preparation(
        input_csv=raw_csv,
        base_dir=base_dir,
        run_id="03-11-2026-00"
    )

    run_id = result["run_id"]
    assert run_id == "03-11-2026-00"

    # Check processed data
    assert (base_dir / "data" / "datasets" / "processed" / run_id / "cleaned.csv").exists()
    assert (base_dir / "data" / "datasets" / "processed" / run_id / "quarantined.csv").exists()

    # Check splits
    assert (base_dir / "data" / "datasets" / "splits" / run_id / "split_assignments.csv").exists()

    # Check preparation artifacts
    prep_dir = base_dir / "artifacts" / "preparation" / run_id
    assert (prep_dir / "manifest.json").exists()
    assert (prep_dir / "profile.json").exists()
    assert (prep_dir / "validation_report.json").exists()
    assert (prep_dir / "cleaning_report.json").exists()
    assert (prep_dir / "split_report.json").exists()

    # Check models artifact
    assert (base_dir / "artifacts" / "models" / run_id / "tfidf.joblib").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_run_full_preparation_synthetic_end_to_end -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.preparation.run_preparation'`

- [ ] **Step 3: Implement `pipeline/preparation/run_preparation.py`**

- Orchestration steps:
  1. Resolve or generate synchronized ID `DD-MM-YYYY-stt`.
  2. Run `inspect_dataset` on raw CSV -> saves to `artifacts/preparation/<run-id>/`.
  3. Run `validate_dataset` on raw CSV -> saves reports to `artifacts/preparation/<run-id>/`.
  4. Run `clean_dataset` -> saves to `data/datasets/processed/<dataset-version>/` and `artifacts/preparation/<run-id>/`.
  5. Run `split_dataset` on `cleaned.csv` -> saves to `data/datasets/splits/<split-version>/` and `artifacts/preparation/<run-id>/`.
  6. Run `IntentFeaturePipeline` fit on the train partition of `split_assignments.csv` -> saves `tfidf.joblib` to `artifacts/models/<run-id>/`.
  7. Generate `manifest.json` cataloging all input hashes, output file paths, sample counts, and execution timestamps.
- Implement CLI with `--input`, `--run-id`, `--dataset-version`, `--split-version`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -k test_run_full_preparation_synthetic_end_to_end -v`  
Expected: PASS

- [ ] **Step 5: Run full test suite to verify 100% pass rate**

Run: `.\.venv\Scripts\pytest tests/unit/test_preparation.py -v`  
Expected: All tests PASS.

- [ ] **Step 6: Execute full preparation pipeline on real Bitext dataset**

Run: `.\.venv\Scripts\python -m pipeline.preparation.run_preparation --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv`  
Verify: Check that `data/datasets/processed/03-11-2026-00/`, `data/datasets/splits/03-11-2026-00/`, `artifacts/preparation/03-11-2026-00/`, and `artifacts/models/03-11-2026-00/` are populated correctly with no leakage detected.

- [ ] **Step 7: Commit**

```bash
git add pipeline/preparation/run_preparation.py tests/unit/test_preparation.py
git commit -m "feat(pipeline): add end-to-end preparation orchestrator and verification tests"
```
