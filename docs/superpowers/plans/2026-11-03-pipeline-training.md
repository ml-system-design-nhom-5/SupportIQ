# Training Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiện thực `pipeline/training/` để huấn luyện, so sánh ba baseline (MultinomialNB, LogisticRegression, LinearSVC) bằng 10-fold CV, khóa winner trước test, refit ba mô hình tốt nhất và xuất bundle/báo cáo/manifest có thể tái lập cho Evaluation.

**Architecture:** Một package Python nhỏ gồm `models.py` (config + factory), `cross_validate.py` (vòng lặp fold, metrics, lựa chọn, OOF, refit), `artifacts.py` (bundle suy luận + ghi file nguyên tử) và `run_training.py` (xác minh hợp đồng dữ liệu, điều phối, manifest). Mỗi fold tạo TF-IDF mới chỉ từ train fold; test chỉ được đọc để xác minh ID/nhãn/nhóm/checksum, không bao giờ fit, transform hay predict.

**Tech Stack:** Python 3.12, pandas 3.1.0, numpy 2.5.4, scikit-learn 1.9.1, scipy 1.18.1, joblib 1.6.0, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-pipeline-training-design.md`

## Global Constraints

- Python `>=3.12`; chạy bằng `.venv` tại gốc repo. Không thêm thư viện mới; config là JSON, không dùng YAML.
- Ba model ID cố định: `multinomial_nb`, `logistic_regression`, `linear_svm`. Grid đúng spec: `alpha: [0.1, 0.5, 1.0]`, `C: [0.1, 1.0, 10.0]`.
- `n_folds=10`, `seed=42`, `cv_target_macro_f1=0.85`; 46 intent lấy từ `pipeline.preparation.utils.STANDARD_INTENTS`; 12 core intent từ `CORE_PRODUCT_INTENTS`.
- TF-IDF: word n-gram `(1, 2)`, `max_features=10000`, `min_df=2`, `sublinear_tf=True`, `lowercase=True`, `token_pattern` mặc định của `IntentFeaturePipeline`.
- Huấn luyện lại TF-IDF mới cho từng fold; tuyệt đối không dùng `artifacts/models/<prep-run>/tfidf.joblib` để đánh giá CV và không ghi đè artifact Preparation.
- Không sửa `IntentFeaturePipeline`, không biến nó thành `BaseEstimator`; Training dùng vòng lặp tường minh và khởi tạo transformer/estimator mới cho từng lượt.
- Test là hold-out bất khả xâm phạm: không fit/transform/predict trên test, không dùng phân bố test để chọn tham số. Test chỉ được đọc ở bước xác minh.
- Nhãn dùng danh mục cố định `sorted(expected_intents)` với `zero_division=0`; không tự bỏ lớp, giảm fold, sửa nhãn hay chia lại dữ liệu.
- Run ID Training là bất biến: không có `--overwrite`; thư mục đã tồn tại phải bị từ chối trước khi ghi. Không commit model/báo cáo; thêm `/artifacts/training/` vào `.gitignore`.
- Mọi artifact nằm dưới `artifacts/training/<run-id>/`; manifest `completed` chỉ được ghi cuối cùng và chỉ sau khi checksum đầu ra hợp lệ.
- Các quyết định ở spec §10 (JSON config, vòng lặp CV tường minh, dừng run khi lỗi hội tụ, lưu cả ba refit, tie-break xác định, run ID không ghi đè) được coi là đã duyệt trong kế hoạch này.

## Review Focus

1. **Rò rỉ test vào lựa chọn:** đổi riêng nội dung test (và cập nhật checksum fixture) phải không làm đổi CV score, winner hay OOF. Test: `test_test_changes_do_not_change_selection` (Task 8), `test_fold_transformer_excludes_validation_only_token` (Task 5), `test_verify_inputs_returns_no_test_text` (Task 3).
2. **Transformer cũ/tái sử dụng giữa fold:** vocabulary và IDF của fold trước không được xuất hiện ở fold sau, và validation-only token không được vào vocabulary. Test: Task 5.
3. **Thiếu lớp trong fold/test bị bỏ qua âm thầm:** các intent hiếm (ví dụ `sales_period`) phải có mặt ở train, validation từng fold và test; thiếu là lỗi, không tự giảm fold. Test: Task 4.
4. **Thứ tự nhãn và core-intent metrics:** confusion matrix và per-class metrics phải theo `class_order` cố định; macro 12 intent tính trên OOF 46 lớp, không lọc bỏ mẫu ngoài 12 intent (false positive từ lớp khác vẫn tính). Test: Task 6.
5. **Lỗi hội tụ hoặc lỗi giữa run bị xuất bản như thành công:** `ConvergenceWarning`, input đổi giữa run, hoặc fit lỗi phải để lại `run_state=failed`, không có `manifest.json` completed. Test: Task 5, Task 8.

---

### Task 1: Cấu hình huấn luyện và model factory

**Files:**
- Create: `pipeline/training/__init__.py`
- Create: `pipeline/training/models.py`
- Create: `pipeline/configs/training.json`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: `pipeline.preparation.utils.STANDARD_INTENTS`, `CORE_PRODUCT_INTENTS`.
- Produces:
  - `TrainingError(Exception)` trong `pipeline/training/__init__.py`.
  - `CandidateSpec(candidate_id: str, model_id: str, order: int, params: dict[str, Any])` (frozen dataclass).
  - `SUPPORTED_MODEL_IDS: frozenset[str]`.
  - `load_training_config(path: str | Path) -> dict[str, Any]`.
  - `validate_training_config(config: dict[str, Any]) -> dict[str, Any]` (trả bản chuẩn hóa, không mutate input).
  - `expand_candidates(config: dict[str, Any]) -> list[CandidateSpec]`.
  - `build_estimator(spec: CandidateSpec, config: dict[str, Any]) -> BaseEstimator` (instance mới mỗi lần gọi).
  - `compute_config_hash(config: dict[str, Any]) -> str` (SHA-256 trên JSON canonical `sort_keys=True`, `separators=(",", ":")`, UTF-8).

- [ ] **Step 1: Viết test thất bại**

```python
# tests/unit/test_training.py
# Đầu file: import json, warnings, dataclasses, pathlib, numpy, pandas, pytest,
# sklearn, sklearn.exceptions.ConvergenceWarning, sklearn.linear_model.LogisticRegression,
# sklearn.svm.LinearSVC; REPO_ROOT = Path(__file__).resolve().parents[2].
CONFIG_PATH = REPO_ROOT / "pipeline" / "configs" / "training.json"

def test_shipped_config_expands_to_nine_candidates():
    config = load_training_config(CONFIG_PATH)
    candidates = expand_candidates(config)
    assert [c.model_id for c in candidates] == (
        ["multinomial_nb"] * 3 + ["logistic_regression"] * 3 + ["linear_svm"] * 3
    )
    assert candidates[0].candidate_id == "multinomial_nb__alpha=0.1"
    assert config["n_folds"] == 10
    assert config["cv_target_macro_f1"] == 0.85
    assert config["seed"] == 42

@pytest.mark.parametrize("mutate", [
    lambda c: c["models"].append(dict(c["models"][0])),
    lambda c: c["models"][0].update(grid={"alpha": []}),
    lambda c: c["models"][0].update(grid={"alpha": [0.0]}),
    lambda c: c["models"][0].update(model_id="random_forest"),
    lambda c: c.update(n_folds=1),
    lambda c: c["tfidf"].update(ngram_range=[2, 1]),
    lambda c: c.update(unknown_key=1),
])
def test_invalid_config_is_rejected(mutate):
    config = load_training_config(CONFIG_PATH)
    mutate(config)
    with pytest.raises(ValueError):
        validate_training_config(config)

def test_build_estimator_applies_params_and_returns_fresh_instance():
    config = load_training_config(CONFIG_PATH)
    candidates = {c.model_id: c for c in expand_candidates(config)}
    lr_a = build_estimator(candidates["logistic_regression"], config)
    lr_b = build_estimator(candidates["logistic_regression"], config)
    assert lr_a is not lr_b
    assert lr_a.get_params()["solver"] == "lbfgs"
    assert lr_a.get_params()["max_iter"] == 2000
    svm = build_estimator(candidates["linear_svm"], config)
    assert svm.get_params()["dual"] == "auto"
    assert svm.get_params()["random_state"] == 42

def test_config_hash_is_canonical_and_value_sensitive():
    assert compute_config_hash({"b": 1, "a": 2}) == compute_config_hash({"a": 2, "b": 1})
    assert compute_config_hash({"a": 2}) != compute_config_hash({"a": 3})
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "shipped_config or invalid_config or build_estimator or config_hash" -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'pipeline.training'`.

- [ ] **Step 3: Tạo config và hiện thực `models.py`**

Tạo `pipeline/configs/training.json` đúng nội dung sau:

```json
{
  "schema_version": 1,
  "seed": 42,
  "n_folds": 10,
  "cv_target_macro_f1": 0.85,
  "tfidf": {
    "ngram_range": [1, 2],
    "max_features": 10000,
    "min_df": 2,
    "sublinear_tf": true,
    "lowercase": true
  },
  "models": [
    {
      "model_id": "multinomial_nb",
      "estimator": "MultinomialNB",
      "grid": {"alpha": [0.1, 0.5, 1.0]},
      "fixed_params": {"fit_prior": true}
    },
    {
      "model_id": "logistic_regression",
      "estimator": "LogisticRegression",
      "grid": {"C": [0.1, 1.0, 10.0]},
      "fixed_params": {"solver": "lbfgs", "max_iter": 2000, "tol": 0.0001, "class_weight": null}
    },
    {
      "model_id": "linear_svm",
      "estimator": "LinearSVC",
      "grid": {"C": [0.1, 1.0, 10.0]},
      "fixed_params": {"dual": "auto", "max_iter": 5000, "tol": 0.0001, "class_weight": null, "random_state": 42}
    }
  ],
  "tie_break": ["macro_f1_mean_desc", "macro_f1_std_asc", "config_order"]
}
```

Quy tắc validation (ném `ValueError` với thông điệp nêu tên trường):
- Top-level chỉ chấp nhận `schema_version, seed, n_folds, cv_target_macro_f1, tfidf, models, tie_break`; `schema_version == 1`, `n_folds` nguyên `>= 2`, `seed` nguyên `>= 0`, target trong `(0, 1]`.
- `tfidf` chỉ chấp nhận 5 khóa ở trên; `ngram_range` là cặp `1 <= low <= high`; `max_features` là `None` hoặc số nguyên dương; `min_df` số nguyên dương; hai cờ bool.
- `models` không rỗng, `model_id` duy nhất và thuộc `SUPPORTED_MODEL_IDS`; `estimator` phải khớp mapping cố định (`multinomial_nb -> MultinomialNB`, `logistic_regression -> LogisticRegression`, `linear_svm -> LinearSVC`).
- Mỗi `grid` là dict không rỗng, khóa là tham số của estimator, mỗi danh sách không rỗng; với `alpha`/`C` mọi giá trị là số thực `> 0`. `fixed_params` là dict và không trùng khóa với `grid`. `tie_break` đúng ba giá trị trong file.
- `expand_candidates`: duyệt `models` theo thứ tự file, khóa grid theo thứ tự sorted, giá trị theo thứ tự trong danh sách; `order` là chỉ số tăng dần; `candidate_id = f"{model_id}__" + ",".join(f"{k}={v}" for k, v in sorted(params.items()))`.

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "shipped_config or invalid_config or build_estimator or config_hash" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/__init__.py pipeline/training/models.py pipeline/configs/training.json tests/unit/test_training.py
git commit -m "feat(training): add training config, validation, and estimator factory"
```

---

### Task 2: Bundle suy luận và ghi artifact nguyên tử

**Files:**
- Create: `pipeline/training/artifacts.py`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: `pipeline.preparation.features.IntentFeaturePipeline`, `pipeline.preparation.utils.compute_sha256`, `load_json`.
- Produces:
  - `IntentModelBundle(transformer, classifier, model_id, candidate_id, classes_, metadata)` với `predict(texts) -> np.ndarray`, `decision_function(texts) -> np.ndarray`, `predict_proba(texts) -> np.ndarray`, `save(model_dir) -> Path`, classmethod `load(model_dir)`.
  - `save_bundle(bundle, model_dir: Path | str) -> Path` (ghi `bundle.joblib`).
  - `load_bundle(model_dir: Path | str) -> IntentModelBundle`.
  - `write_json_atomic(data, path)` và `write_csv_atomic(df, path)` (temp file cùng thư mục + `os.replace`).

- [ ] **Step 1: Viết test thất bại**

```python
TEXTS = ["track my order", "cancel my order", "refund status", "where is my parcel"]
LABELS = ["track_order", "cancel_order", "refund_status", "track_order"]

def _fit_tiny_bundle(model_id="logistic_regression"):
    transformer = IntentFeaturePipeline(min_df=1, max_features=50).fit(TEXTS)
    if model_id == "linear_svm":
        classifier = LinearSVC(C=1.0, dual="auto", max_iter=5000, random_state=42)
    else:
        classifier = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
    classifier.fit(transformer.transform(TEXTS), LABELS)
    return IntentModelBundle(
        transformer=transformer, classifier=classifier, model_id=model_id,
        candidate_id=f"{model_id}__C=1.0", classes_=list(classifier.classes_),
        metadata={"sklearn_version": sklearn.__version__},
    )

def test_bundle_roundtrip_and_text_normalization(tmp_path):
    bundle = _fit_tiny_bundle()
    reference = bundle.predict(["track my order"]).tolist()
    assert bundle.predict(["ＴＲＡＣＫ   ＭＹ   ＯＲＤＥＲ"]).tolist() == reference
    saved = save_bundle(bundle, tmp_path / "models" / "logistic_regression")
    loaded = load_bundle(saved.parent)
    assert loaded.predict(TEXTS).tolist() == bundle.predict(TEXTS).tolist()

def test_bundle_scores_follow_classes_order():
    bundle = _fit_tiny_bundle("linear_svm")
    scores = bundle.decision_function(TEXTS)
    predicted = bundle.predict(TEXTS).tolist()
    assert predicted == [bundle.classes_[i] for i in scores.argmax(axis=1)]

def test_svm_bundle_does_not_fake_probabilities():
    bundle = _fit_tiny_bundle("linear_svm")
    with pytest.raises(AttributeError):
        bundle.predict_proba(TEXTS)

def test_atomic_json_write_replaces_without_leftovers(tmp_path):
    target = tmp_path / "run" / "run_state.json"
    write_json_atomic({"status": "running"}, target)
    write_json_atomic({"status": "completed"}, target)
    assert load_json(target) == {"status": "completed"}
    assert [p.name for p in target.parent.iterdir()] == ["run_state.json"]
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "bundle or atomic_json" -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'pipeline.training.artifacts'`.

- [ ] **Step 3: Hiện thực `artifacts.py`**

- `predict/decision_function/predict_proba` luôn gọi `transformer.transform(texts)` trước rồi mới gọi classifier; không yêu cầu caller chuẩn hóa (transformer đã NFKC + whitespace + lowercase).
- `predict_proba`/`decision_function`: nếu classifier không có method tương ứng, ném `AttributeError` nêu rõ `model_id`; không tự tạo xác suất giả cho SVM.
- `__init__` kiểm tra `list(classifier.classes_) == list(classes_)`; lưu `classes_` dạng `list[str]`.
- `save_bundle` dùng `joblib.dump` ra `<model_dir>/.bundle.joblib.tmp` rồi `os.replace` thành `bundle.joblib`; `load_bundle` kiểm tra file tồn tại và instance type.
- `write_json_atomic`/`write_csv_atomic` tạo thư mục cha, ghi `.tmp` cùng thư mục, `os.replace`; JSON dùng `indent=2, ensure_ascii=False`.

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "bundle or atomic_json" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/artifacts.py tests/unit/test_training.py
git commit -m "feat(training): add inference bundle and atomic artifact writers"
```

---

### Task 3: Xác minh manifest, checksum, schema và phủ ID

**Files:**
- Create: `pipeline/training/run_training.py`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: `pipeline.preparation.utils` (`compute_sha256`, `load_json`, `save_json`, `STANDARD_INTENTS`, `get_near_duplicate_key`).
- Produces:
  - `VerifiedInputs(development: pd.DataFrame, test_sample_ids: tuple[str, ...], class_order: tuple[str, ...], manifest: dict, split_report: dict, paths: dict[str, Path], checksums: dict[str, str])` (frozen dataclass).
  - `verify_inputs(preparation_manifest: Path | str, *, expected_intents: Collection[str] = STANDARD_INTENTS, n_folds: int = 10) -> VerifiedInputs`.
  - Fixture test dùng chung: `PrepFixture` và `make_prep_fixture(tmp_path, *, intents=("alpha", "beta", "gamma"), n_folds=2, samples_per_class_fold=2)`.
  - `rewrite_fixture(fx: PrepFixture) -> None`: ghi lại CSV, tính lại `cleaned_sha256`/`splits_sha256`, cập nhật `summary` và `metadata` số lượng.

- [ ] **Step 1: Viết fixture và test thất bại**

```python
@dataclass
class PrepFixture:
    root: Path
    manifest_path: Path
    cleaned_path: Path
    splits_path: Path
    report_path: Path
    cleaned: pd.DataFrame
    assignments: pd.DataFrame

def make_prep_fixture(tmp_path, intents=("alpha", "beta", "gamma"), n_folds=2,
                      samples_per_class_fold=2) -> PrepFixture:
    rows = []
    for intent in intents:
        for fold in range(n_folds):
            for i in range(samples_per_class_fold):
                rows.append({"sample_id": f"{intent}-{fold}-{i}",
                             "instruction": f"{intent} development question {fold} {i}",
                             "intent": intent, "category": "CAT"})
        rows.append({"sample_id": f"{intent}-test", "instruction": f"{intent} heldout question",
                     "intent": intent, "category": "CAT"})
    cleaned = pd.DataFrame(rows)
    assignments = pd.DataFrame({
        "sample_id": cleaned["sample_id"],
        "partition": np.where(cleaned["sample_id"].str.endswith("-test"), "test", "train"),
        "fold": cleaned["sample_id"].str.extract(r"-(\d+)-\d+$")[0].astype("Int64").fillna(-1).astype(int),
    })
    cleaned_path = tmp_path / "cleaned.csv"
    splits_path = tmp_path / "split_assignments.csv"
    report_path = tmp_path / "split_report.json"
    manifest_path = tmp_path / "manifest.json"
    cleaned.to_csv(cleaned_path, index=False)
    assignments.to_csv(splits_path, index=False)
    fx = PrepFixture(tmp_path, manifest_path, cleaned_path, splits_path, report_path, cleaned, assignments)
    rewrite_fixture(fx)
    return fx

def test_verify_inputs_returns_development_only(tmp_path):
    fx = make_prep_fixture(tmp_path)
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    assert len(verified.development) == 12
    assert len(verified.test_sample_ids) == 3
    assert set(verified.development["sample_id"]).isdisjoint(verified.test_sample_ids)
    assert verified.class_order == ("alpha", "beta", "gamma")

def test_verify_inputs_returns_no_test_text(tmp_path):
    fx = make_prep_fixture(tmp_path)
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    test_text = set(fx.cleaned.loc[fx.cleaned["sample_id"].str.endswith("-test"), "instruction"])
    assert test_text.isdisjoint(set(verified.development["instruction"]))

def test_verify_inputs_rejects_checksum_mismatch(tmp_path):
    fx = make_prep_fixture(tmp_path)
    report = load_json(fx.report_path)
    report["cleaned_sha256"] = "0" * 64
    save_json(report, fx.report_path)
    with pytest.raises(ValueError, match="cleaned_sha256"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)

@pytest.mark.parametrize("break_ids", ["missing", "duplicate", "extra"])
def test_verify_inputs_rejects_bad_id_coverage(tmp_path, break_ids):
    fx = make_prep_fixture(tmp_path)
    if break_ids == "missing":
        fx.assignments = fx.assignments.iloc[:-1]
    elif break_ids == "duplicate":
        fx.assignments = pd.concat([fx.assignments, fx.assignments.iloc[[0]]])
    else:
        extra = fx.assignments.iloc[[0]].assign(sample_id="not-in-cleaned")
        fx.assignments = pd.concat([fx.assignments, extra])
    rewrite_fixture(fx)
    with pytest.raises(ValueError):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)

def test_verify_inputs_rejects_count_mismatch(tmp_path):
    fx = make_prep_fixture(tmp_path)
    manifest = load_json(fx.manifest_path)
    manifest["metadata"]["train_samples"] += 1
    save_json(manifest, fx.manifest_path)
    with pytest.raises(ValueError, match="train_samples"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "verify_inputs" -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'pipeline.training.run_training'`.

- [ ] **Step 3: Hiện thực phần xác minh đầu tiên trong `run_training.py`**

`rewrite_fixture` ghi `split_report.json` với `cleaned_sha256`, `splits_sha256`, `summary.total_samples/train_samples/test_samples`; ghi `manifest.json` với `run_id="prep-fixture"`, `metadata.dataset_version="03-11-2026-02"`, `metadata.split_version="03-11-2026-02"`, `metadata.cleaned_samples/train_samples/test_samples`, và `output_artifacts.cleaned_csv/split_assignments/split_report` trỏ đúng file. Sau đó:

- Resolve đường dẫn artifact: đường dẫn tuyệt đối dùng nguyên; đường dẫn tương đối tính từ `repo_root` (tham số `repo_root: Path = REPO_ROOT`, với `REPO_ROOT = Path(__file__).resolve().parents[2]`), không từ `Path.cwd()`.
- `verify_inputs` đọc manifest JSON; bắt buộc `run_id`, `metadata.dataset_version`, `metadata.split_version`, `metadata.cleaned_samples/train_samples/test_samples` và `output_artifacts.cleaned_csv/split_assignments/split_report`.
- Đọc `cleaned.csv` với pandas; bắt buộc cột `sample_id, instruction, intent, category`; `sample_id` không rỗng/không trùng; `instruction`/`intent`/`category` không rỗng; `intent` thuộc `expected_intents`; tập intent thực tế bằng đúng `expected_intents`.
- Đọc `split_assignments.csv`; bắt buộc cột `sample_id, partition, fold`; ID không trùng; tập ID bằng chính xác tập ID cleaned (không thiếu, không dư). Join one-to-one bằng `merge(..., how="left", validate="one_to_one")`; không dùng inner join.
- Đọc `split_report.json`; tính lại `compute_sha256` cho cleaned và assignments, so với `cleaned_sha256`/`splits_sha256`; so `summary.total_samples/train_samples/test_samples` với dữ liệu và `manifest.metadata` tương ứng.
- Trả `development` chỉ gồm `partition == "train"` với các cột `sample_id, instruction, intent, category, fold`; `test_sample_ids` chỉ là tuple ID, không kèm instruction. `class_order = tuple(sorted(expected_intents))`; `checksums` chứa hash thực tế của cleaned/splits/report.
- Mọi vi phạm ném `ValueError` với tên trường/điều kiện trong thông điệp; không tự sửa dữ liệu.

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "verify_inputs" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/run_training.py tests/unit/test_training.py
git commit -m "feat(training): verify preparation manifest, checksums, and sample coverage"
```

---

### Task 4: Xác minh partition, fold, phủ lớp và nhóm gần trùng

**Files:**
- Modify: `pipeline/training/run_training.py`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: `verify_inputs`, `get_near_duplicate_key`, `VerifiedInputs`.
- Produces: `VerifiedInputs.development` có thêm cột `group_key`; `verify_inputs` thực hiện đầy đủ các kiểm tra leakage và phủ lớp. Không đổi chữ ký hàm.

- [ ] **Step 1: Viết test thất bại**

```python
def _fold_column(fx, fold):
    fx.assignments.loc[fx.assignments["fold"] == fold, "fold"] = 99
    rewrite_fixture(fx)

def test_verify_inputs_rejects_test_fold_not_minus_one(tmp_path):
    fx = make_prep_fixture(tmp_path)
    fx.assignments.loc[fx.assignments["partition"] == "test", "fold"] = 0
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="test.*fold"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)

def test_verify_inputs_rejects_missing_or_empty_fold(tmp_path):
    fx = make_prep_fixture(tmp_path)
    _fold_column(fx, 1)  # không còn fold 1 trong 0..1
    with pytest.raises(ValueError, match="fold"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)

def test_verify_inputs_rejects_intent_missing_from_fold_validation(tmp_path):
    fx = make_prep_fixture(tmp_path)
    mask = (fx.cleaned["intent"] == "gamma") & fx.cleaned["sample_id"].isin(
        fx.assignments.loc[fx.assignments["fold"] == 1, "sample_id"]
    )
    fx.assignments.loc[fx.assignments["sample_id"].isin(fx.cleaned.loc[mask, "sample_id"]), "fold"] = 0
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="validation fold 1"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)

def test_verify_inputs_rejects_near_duplicate_group_across_folds(tmp_path):
    fx = make_prep_fixture(tmp_path)
    fold0_id = fx.assignments.loc[fx.assignments["fold"] == 0, "sample_id"].iloc[0]
    fold1_id = fx.assignments.loc[fx.assignments["fold"] == 1, "sample_id"].iloc[0]
    text = fx.cleaned.loc[fx.cleaned["sample_id"] == fold0_id, "instruction"].iloc[0]
    fx.cleaned.loc[fx.cleaned["sample_id"] == fold1_id, "instruction"] = text.upper() + "!!!"
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="group"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)

def test_verify_inputs_rejects_conflicting_group_labels(tmp_path):
    fx = make_prep_fixture(tmp_path)
    first, second = fx.assignments["sample_id"].iloc[0], fx.assignments["sample_id"].iloc[1]
    text = fx.cleaned.loc[fx.cleaned["sample_id"] == first, "instruction"].iloc[0]
    fx.cleaned.loc[fx.cleaned["sample_id"] == second, "instruction"] = text
    fx.cleaned.loc[fx.cleaned["sample_id"] == second, "intent"] = "beta"
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="conflicting"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "test_fold or empty_fold or missing_from_fold or near_duplicate or conflicting_group" -v`
Expected: FAIL — các trường hợp sai hiện chưa bị từ chối.

- [ ] **Step 3: Bổ sung kiểm tra vào `verify_inputs`**

Thứ tự kiểm tra: ID/checksum → partition/fold layout → nhóm → phủ lớp (để thông điệp lỗi nhóm không bị che bởi lỗi thiếu lớp).
- `partition` chỉ chứa `{"train", "test"}`. Test phải có `fold == -1` (thông điệp chứa `test` và `fold`); development phải có đúng tập fold `set(range(n_folds))`, mỗi fold `0..n_folds-1` không rỗng.
- Join assignments với cleaned, tính `group_key = instruction.apply(get_near_duplicate_key)`; mỗi `group_key` chỉ thuộc một partition và một fold (thông điệp chứa `group`); một `group_key` chỉ có một `intent` (nếu khác nhau, ném lỗi chứa `conflicting`).
- Mỗi intent trong `expected_intents` phải xuất hiện ở train và validation của từng fold, và trong test; thiếu validation fold `k` phải ném thông điệp dạng `intent '<name>' missing from validation fold <k>`. Không tự giảm fold hay bỏ lớp.
- Gắn `group_key` vào `development` trả về.

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "verify_inputs" -v`
Expected: PASS toàn bộ test của Task 3 và Task 4.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/run_training.py tests/unit/test_training.py
git commit -m "feat(training): enforce fold layout, class coverage, and group isolation"
```

---

### Task 5: Vòng lặp CV với TF-IDF mới cho từng fold

**Files:**
- Create: `pipeline/training/cross_validate.py`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: `pipeline.preparation.features.IntentFeaturePipeline`, `CandidateSpec`, `build_estimator`, `TrainingError`.
- Produces:
  - `build_fold_features(train_texts, validation_texts, tfidf_config) -> tuple[IntentFeaturePipeline, csr_matrix, csr_matrix, float]`.
  - `CVResult(fold_metrics: pd.DataFrame, oof_predictions: pd.DataFrame)`.
  - `run_cross_validation(development, config, candidates, *, class_order, on_fold: Callable[[pd.DataFrame], None] | None = None) -> CVResult`.

- [ ] **Step 1: Viết test thất bại**

```python
def test_fold_transformer_excludes_validation_only_token():
    transformer, _, _, _ = build_fold_features(
        ["alpha common token", "beta common token"],
        ["gamma zzonlyval token"],
        {"ngram_range": (1, 1), "max_features": 100, "min_df": 1,
         "sublinear_tf": True, "lowercase": True},
    )
    assert "zzonlyval" not in transformer.get_feature_names()

def test_cross_validation_runs_every_candidate_and_fold(tmp_path):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    result = run_cross_validation(verified.development, config, expand_candidates(config),
                                  class_order=verified.class_order)
    assert len(result.fold_metrics) == 6 * 2
    assert result.fold_metrics.groupby("candidate_id")["fold"].nunique().eq(2).all()
    assert (result.fold_metrics["status"] == "ok").all()
    assert (result.fold_metrics["transform_seconds"] >= 0).all()
    assert (result.fold_metrics["fit_seconds"] >= 0).all()
    assert (result.fold_metrics["predict_seconds"] >= 0).all()

def test_convergence_warning_fails_the_run(tmp_path, monkeypatch):
    def fake_fit(self, X, y):
        warnings.warn("did not converge", ConvergenceWarning)
        self.classes_ = np.array(sorted(set(y)))
        return self

    monkeypatch.setattr(LogisticRegression, "fit", fake_fit)
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    with pytest.raises(TrainingError, match="ConvergenceWarning"):
        run_cross_validation(verified.development, config, expand_candidates(config),
                             class_order=verified.class_order)

def test_nan_metric_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.training.cross_validate.f1_score",
                        lambda *args, **kwargs: float("nan"))
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    with pytest.raises(TrainingError, match="NaN"):
        run_cross_validation(verified.development, config, expand_candidates(config),
                             class_order=verified.class_order)
```

`make_cv_config()` là helper test: config hợp lệ với `n_folds=2`, TF-IDF `ngram_range=[1,1]`, `max_features=100`, `min_df=1`, và mỗi model grid 2 giá trị (tổng 6 candidate), dùng `validate_training_config` để chuẩn hóa.

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "fold_transformer or cross_validation or convergence or nan_metric" -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'pipeline.training.cross_validate'`.

- [ ] **Step 3: Hiện thực `cross_validate.py`**

- `build_fold_features`: tạo `IntentFeaturePipeline(**tfidf_config)` mới (chuẩn hóa `ngram_range=list` từ JSON thành tuple); `fit_transform(train_texts)`, `transform(validation_texts)`; đo thời gian transform bằng `time.perf_counter()`; nếu vocabulary rỗng → `TrainingError`; trả ma trận sparse, không dense.
- `run_cross_validation`: với mỗi fold `0..n_folds-1`, train là `fold != k`, validation là `fold == k`; gọi `build_fold_features` đúng một lần/fold, dùng lại hai ma trận cho mọi candidate trong fold. Mỗi candidate lấy `build_estimator` mới, fit trong `warnings.catch_warnings(record=True)` với `simplefilter("always")`.
- Nếu có `ConvergenceWarning`: ghi hàng fold với `status="failed"`, `warnings` chứa thông điệp, gọi `on_fold` với dữ liệu tích lũy, rồi ném `TrainingError("ConvergenceWarning: ...")`; không chạy tiếp candidate/fold khác.
- Nếu bất kỳ metric nào là NaN/Inf: ghi hàng `status="failed"` (nếu còn ghi được) rồi ném `TrainingError("NaN metric ...")`; không đưa candidate vào tổng hợp.
- Cột `fold_metrics`: `model_id, candidate_id, params, fold, n_train, n_validation, macro_f1, accuracy, weighted_f1, transform_seconds, fit_seconds, predict_seconds, status, warnings`; `params` là JSON canonical. Metrics dùng `labels=class_order`, `average="macro"/"weighted"`, `zero_division=0`; accuracy từ `accuracy_score`.
- OOF: mỗi dự đoán validation của từng candidate, cột `sample_id, fold, y_true, y_pred, model_id, candidate_id`; giữ tất cả candidate để Task 6 lọc.
- `on_fold` nhận DataFrame tích lũy (các fold đã xong) để orchestrator ghi `fold_metrics.csv` nguyên tử sau mỗi fold.

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "fold_transformer or cross_validation or convergence or nan_metric" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/cross_validate.py tests/unit/test_training.py
git commit -m "feat(training): add per-fold CV loop with fresh TF-IDF and convergence guard"
```

---

### Task 6: Tổng hợp, tie-break, OOF và báo cáo per-class

**Files:**
- Modify: `pipeline/training/cross_validate.py`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: `CVResult`, `CandidateSpec`.
- Produces:
  - `summarize_fold_metrics(fold_metrics, candidates, *, n_folds: int) -> pd.DataFrame` với mean/std (`ddof=0`) của ba metric và cột `eligible`.
  - `SelectionResult(best_per_model: dict[str, str], winner: str, payload: dict[str, Any])`.
  - `select_candidates(summary, candidates, *, target: float) -> SelectionResult`.
  - `build_oof_reports(oof, *, labels, core_intents, report_dir: Path) -> dict[str, dict]` ghi `reports/<model-id>/{per_class_metrics.csv,confusion_matrix.csv,core_intent_metrics.json,top_confusions.csv}` và trả core metrics theo model.

- [ ] **Step 1: Viết test thất bại**

```python
def test_summary_uses_population_std_and_keeps_all_candidates():
    candidates = [CandidateSpec("m__C=0.1", "m", 0, {"C": 0.1}),
                  CandidateSpec("m__C=1.0", "m", 1, {"C": 1.0})]
    fold_metrics = pd.DataFrame([
        {"model_id": "m", "candidate_id": "m__C=0.1", "params": "{}", "fold": 0,
         "macro_f1": 0.5, "accuracy": 0.5, "weighted_f1": 0.5, "status": "ok"},
        {"model_id": "m", "candidate_id": "m__C=0.1", "params": "{}", "fold": 1,
         "macro_f1": 0.7, "accuracy": 0.5, "weighted_f1": 0.5, "status": "ok"},
    ])
    summary = summarize_fold_metrics(fold_metrics, candidates, n_folds=2)
    row = summary.loc[summary["candidate_id"] == "m__C=0.1"].iloc[0]
    assert row["macro_f1_mean"] == pytest.approx(0.6)
    assert row["macro_f1_std"] == pytest.approx(0.1)
    assert len(summary) == 2  # candidate không có fold vẫn còn, eligible=False
    assert not summary.loc[summary["candidate_id"] == "m__C=1.0", "eligible"].iloc[0]

def test_selection_tie_breaks_lower_std_then_config_order():
    candidates = [CandidateSpec("a", "m", 0, {}), CandidateSpec("b", "m", 1, {})]
    summary = pd.DataFrame([
        {"candidate_id": "a", "model_id": "m", "macro_f1_mean": 0.8, "macro_f1_std": 0.02, "eligible": True},
        {"candidate_id": "b", "model_id": "m", "macro_f1_mean": 0.8, "macro_f1_std": 0.01, "eligible": True},
    ])
    assert select_candidates(summary, candidates, target=0.85).winner == "b"
    summary.loc[summary["candidate_id"] == "b", "macro_f1_std"] = 0.02
    assert select_candidates(summary, candidates, target=0.85).winner == "a"

def test_oof_reports_include_false_positives_from_other_classes(tmp_path):
    oof = pd.DataFrame([
        {"sample_id": "1", "fold": 0, "y_true": "beta", "y_pred": "alpha",
         "model_id": "m", "candidate_id": "m__C=1.0"},
    ])
    core = build_oof_reports(oof, labels=("alpha", "beta", "gamma"),
                             core_intents=("alpha",), report_dir=tmp_path)
    assert core["m"]["per_intent"]["alpha"]["precision"] == 0.0
    assert core["m"]["macro_f1"] == 0.0
    matrix = pd.read_csv(tmp_path / "m" / "confusion_matrix.csv", index_col=0)
    assert matrix.shape == (3, 3)
    assert matrix.loc["beta", "alpha"] == 1
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "summary or selection or oof_reports" -v`
Expected: FAIL vì các hàm chưa tồn tại.

- [ ] **Step 3: Hiện thực tổng hợp, lựa chọn và báo cáo**

- `summarize_fold_metrics`: gom theo `(model_id, candidate_id)` cho đủ danh sách candidate (kể cả candidate thiếu fold), mean/std `ddof=0`; `eligible = status toàn bộ "ok" và số fold == n_folds`; sắp theo `order` để tie-break `config_order` ổn định.
- `select_candidates`: chỉ xét `eligible`; nếu một model không có candidate eligible → `TrainingError` (không âm thầm bỏ model). Với từng model chọn `(-round(macro_f1_mean, 6), round(macro_f1_std, 6), order)` nhỏ nhất; winner là candidate có `(-round(mean, 6), round(std, 6), order)` nhỏ nhất trong ba best. `payload` chứa `selection_metric`, `tie_break`, `cv_target_macro_f1`, `meets_cv_target = round(winner_mean, 6) >= target`, `best_per_model` với metrics và params; không gắn nhãn production-ready.
- `build_oof_reports`: mỗi model trong `oof["model_id"]`, dùng `labels` cố định cho `classification_report(..., output_dict=True, zero_division=0)` và `confusion_matrix(labels=labels)`; ghi `per_class_metrics.csv` (index `label`), `confusion_matrix.csv` (index + cột theo đúng `labels`), `core_intent_metrics.json` (per-intent precision/recall/F1/support + macro trung bình đúng các nhãn core, tính từ metrics 46 lớp nên vẫn giữ false positive từ lớp khác), `top_confusions.csv` (cặp `y_true,y_pred` khác nhau, đếm giảm dần, tối đa 20). Không lọc bỏ sample ngoài core trước khi tính.

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "summary or selection or oof_reports" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/cross_validate.py tests/unit/test_training.py
git commit -m "feat(training): add candidate summary, deterministic selection, and OOF reports"
```

---

### Task 7: Refit trên toàn development, bundle và model card

**Files:**
- Modify: `pipeline/training/cross_validate.py`
- Modify: `pipeline/training/artifacts.py`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: `IntentModelBundle`, `IntentFeaturePipeline`, `CandidateSpec`, `SelectionResult`.
- Produces:
  - `refit_final_models(development, config, candidates, best_per_model, *, metadata=None) -> dict[str, IntentModelBundle]`.
  - `build_model_card(*, run_id, model_id, candidate_id, params, resolved_params, cv_metrics, preparation_run_id, dataset_version, split_version, class_order, core_intents, target_met) -> dict[str, Any]`.

- [ ] **Step 1: Viết test thất bại**

```python
def test_refit_fits_one_transformer_on_all_development_rows(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    calls = []
    real_fit_transform = IntentFeaturePipeline.fit_transform

    def spy(self, texts):
        calls.append(list(texts))
        return real_fit_transform(self, texts)

    monkeypatch.setattr(IntentFeaturePipeline, "fit_transform", spy)
    candidates = expand_candidates(config)
    best = {m: next(c.candidate_id for c in candidates if c.model_id == m)
            for m in ("multinomial_nb", "logistic_regression", "linear_svm")}
    bundles = refit_final_models(verified.development, config, candidates, best)
    assert list(calls[0]) == list(verified.development["instruction"])
    assert len(bundles) == 3

def test_refit_bundle_predicts_like_classifier_and_reloads(tmp_path):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    candidates = expand_candidates(config)
    best = {m: next(c.candidate_id for c in candidates if c.model_id == m) for m in
            ("multinomial_nb", "logistic_regression", "linear_svm")}
    bundles = refit_final_models(verified.development, config, candidates, best)
    for model_id, bundle in bundles.items():
        expected = bundle.classifier.predict(bundle.transformer.transform(TEXTS)).tolist()
        assert bundle.predict(TEXTS).tolist() == expected
        loaded = load_bundle(save_bundle(bundle, tmp_path / "models" / model_id).parent)
        assert loaded.predict(TEXTS).tolist() == expected

def test_model_card_records_scope_limits_and_release_gate():
    card = build_model_card(
        run_id="03-11-2026-training-00", model_id="linear_svm", candidate_id="linear_svm__C=1.0",
        params={"C": 1.0}, resolved_params={"C": 1.0, "max_iter": 5000},
        cv_metrics={"macro_f1_mean": 0.8, "macro_f1_std": 0.01},
        preparation_run_id="03-11-2026-02", dataset_version="03-11-2026-02",
        split_version="03-11-2026-02", class_order=("alpha", "beta", "gamma"),
        core_intents=("alpha",), target_met=False,
    )
    assert card["status"] == "candidate"
    assert card["calibration"] == "not_calibrated"
    assert card["languages"] == ["en"]
    assert card["n_labels"] == 3
    assert card["evaluation_required_before_release"] is True
    assert "synthetic" in card["data_limitations"].lower()
    assert card["meets_cv_target"] is False
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "refit or model_card" -v`
Expected: FAIL vì `refit_final_models`/`build_model_card` chưa tồn tại.

- [ ] **Step 3: Hiện thực refit và model card**

- `refit_final_models`: tạo **một** `IntentFeaturePipeline` mới từ `config["tfidf"]` (chuẩn hóa `ngram_range` thành tuple), `fit_transform` trên toàn bộ `development["instruction"]`; với mỗi model trong `best_per_model`, lấy `CandidateSpec` tương ứng, tạo estimator mới và fit trên cùng ma trận + `development["intent"]`. Trả bundle với `classes_ = list(classifier.classes_)`, `candidate_id`, `model_id`, metadata gồm `training_run_id`, `preparation_run_id`, `dataset_version`, `split_version`, `sklearn_version`, `class_order`, `resolved_params = classifier.get_params(deep=False)`. Không đọc test.
- `build_model_card`: trả dict có `model_id`, `candidate_id`, `params`, `resolved_params`, `training_run_id`, `preparation_run_id`, `dataset_version`, `split_version`, `language: "en"`/`languages: ["en"]`, `n_labels`, `classes`, `cv_metrics`, `cv_target_macro_f1`, `meets_cv_target`, `core_intents`, `data_limitations` (câu nêu dữ liệu Bitext tiếng Anh tổng hợp, không phải traffic thật), `calibration: "not_calibrated"`, `abstention_threshold: null`, `status: "candidate"`, `evaluation_required_before_release: True`, `known_limits` (SVM không có predict_proba; LR/NB chưa hiệu chuẩn; chưa đánh giá out-of-scope).

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "refit or model_card" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/cross_validate.py pipeline/training/artifacts.py tests/unit/test_training.py
git commit -m "feat(training): refit selected models on development and emit model cards"
```

---

### Task 8: Orchestrator, run state, environment, manifest và CLI

**Files:**
- Modify: `pipeline/training/run_training.py`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: toàn bộ hàm Task 1–7.
- Produces:
  - `capture_environment(repo_root: Path) -> dict[str, Any]`.
  - `load_completed_manifest(run_dir: Path | str) -> dict[str, Any]` (từ chối status khác `completed`, checksum sai).
  - `validate_run_id(run_id: str) -> str` (chấp nhận `DD-MM-YYYY-<suffix>` với suffix chữ/số/`-`/`_`, từ chối `/`, `\`, `..`).
  - `run_training(preparation_manifest, config_path, run_id, output_root, *, expected_intents=STANDARD_INTENTS, repo_root=REPO_ROOT) -> dict[str, Any]` trả ít nhất `run_dir`, `manifest_path`, `selection`.
  - CLI `python -m pipeline.training.run_training --preparation-manifest ... --config ... --run-id ... [--output-root artifacts/training]`.

- [ ] **Step 1: Viết test thất bại**

```python
def _tiny_run(tmp_path, run_id="03-11-2026-training-00"):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    config_path = tmp_path / "config.json"
    save_json(config, config_path)
    result = run_training(fx.manifest_path, config_path, run_id, tmp_path / "artifacts" / "training",
                          expected_intents=("alpha", "beta", "gamma"))
    return fx, Path(result["run_dir"])

def test_run_training_writes_complete_artifact_tree(tmp_path):
    fx, run_dir = _tiny_run(tmp_path)
    for name in ("config.resolved.json", "environment.json", "fold_metrics.csv",
                 "candidate_summary.csv", "selection.json", "oof_predictions.csv", "manifest.json"):
        assert (run_dir / name).exists()
    assert len(pd.read_csv(run_dir / "fold_metrics.csv")) == 6 * 2
    assert len(pd.read_csv(run_dir / "candidate_summary.csv")) == 6
    oof = pd.read_csv(run_dir / "oof_predictions.csv")
    assert oof["model_id"].nunique() == 3
    assert oof.groupby(["model_id", "sample_id"]).size().eq(1).all()
    for model_id in ("multinomial_nb", "logistic_regression", "linear_svm"):
        assert (run_dir / "models" / model_id / "bundle.joblib").exists()
        assert (run_dir / "models" / model_id / "model_card.json").exists()
        assert (run_dir / "reports" / model_id / "confusion_matrix.csv").exists()
    manifest = load_completed_manifest(run_dir)
    assert manifest["status"] == "completed"
    assert manifest["schema_version"] == 1
    for rel, digest in manifest["outputs"].items():
        assert compute_sha256(run_dir / rel) == digest

def test_run_training_refuses_existing_run_id_before_writing(tmp_path):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)
    run_dir = tmp_path / "artifacts" / "training" / "03-11-2026-training-00"
    run_dir.mkdir(parents=True)
    (run_dir / "sentinel.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_training(fx.manifest_path, config_path, run_dir.name, run_dir.parent,
                     expected_intents=("alpha", "beta", "gamma"))
    assert (run_dir / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert not (run_dir / "run_state.json").exists()

def test_failed_run_leaves_failed_state_without_completed_manifest(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)

    def boom(*args, **kwargs):
        raise TrainingError("boom")

    monkeypatch.setattr("pipeline.training.run_training.run_cross_validation", boom)
    with pytest.raises(TrainingError, match="boom"):
        run_training(fx.manifest_path, config_path, "03-11-2026-training-01",
                     tmp_path / "artifacts" / "training",
                     expected_intents=("alpha", "beta", "gamma"))
    run_dir = tmp_path / "artifacts" / "training" / "03-11-2026-training-01"
    assert load_json(run_dir / "run_state.json")["status"] == "failed"
    assert not (run_dir / "manifest.json").exists()

def test_run_fails_when_input_changes_mid_run(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)
    real_cv = run_cross_validation

    def tamper_then_run(*args, **kwargs):
        fx.cleaned.loc[fx.cleaned.index[0], "instruction"] = "mutated during run"
        fx.cleaned.to_csv(fx.cleaned_path, index=False)
        return real_cv(*args, **kwargs)

    monkeypatch.setattr("pipeline.training.run_training.run_cross_validation", tamper_then_run)
    with pytest.raises(TrainingError, match="changed during run"):
        run_training(fx.manifest_path, config_path, "03-11-2026-training-03",
                     tmp_path / "artifacts" / "training",
                     expected_intents=("alpha", "beta", "gamma"))
    run_dir = tmp_path / "artifacts" / "training" / "03-11-2026-training-03"
    assert load_json(run_dir / "run_state.json")["status"] == "failed"
    assert not (run_dir / "manifest.json").exists()

def test_test_changes_do_not_change_selection(tmp_path):
    fx, run_a = _tiny_run(tmp_path, "03-11-2026-training-00")
    selection_a = load_json(run_a / "selection.json")
    oof_a = pd.read_csv(run_a / "oof_predictions.csv")
    metric_cols = ["model_id", "candidate_id", "fold", "macro_f1", "accuracy", "weighted_f1"]
    metrics_a = pd.read_csv(run_a / "fold_metrics.csv")[metric_cols]
    fx.cleaned.loc[fx.cleaned["sample_id"].str.endswith("-test"), "instruction"] = "totally different test text"
    rewrite_fixture(fx)
    result_b = run_training(fx.manifest_path, tmp_path / "config.json", "03-11-2026-training-01",
                            tmp_path / "artifacts" / "training",
                            expected_intents=("alpha", "beta", "gamma"))
    run_b = Path(result_b["run_dir"])
    selection_b = load_json(run_b / "selection.json")
    assert selection_a["winner"] == selection_b["winner"]
    assert selection_a["best_per_model"] == selection_b["best_per_model"]
    pd.testing.assert_frame_equal(oof_a, pd.read_csv(run_b / "oof_predictions.csv"))
    pd.testing.assert_frame_equal(metrics_a, pd.read_csv(run_b / "fold_metrics.csv")[metric_cols])

def test_training_never_transforms_test_text(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)
    seen = []
    real_transform = IntentFeaturePipeline.transform

    def spy(self, texts):
        seen.extend(list(texts))
        return real_transform(self, texts)

    monkeypatch.setattr(IntentFeaturePipeline, "transform", spy)
    run_training(fx.manifest_path, config_path, "03-11-2026-training-02",
                 tmp_path / "artifacts" / "training",
                 expected_intents=("alpha", "beta", "gamma"))
    test_text = set(fx.cleaned.loc[fx.cleaned["sample_id"].str.endswith("-test"), "instruction"])
    assert test_text.isdisjoint(seen)

@pytest.mark.parametrize("bad_run_id", ["../escape", "03-11-2026-a/b", "03-11-2026-a\\b", ""])
def test_invalid_run_id_is_rejected(bad_run_id):
    with pytest.raises(ValueError):
        validate_run_id(bad_run_id)

def test_environment_and_tampered_artifact_rejected(tmp_path):
    _, run_dir = _tiny_run(tmp_path)
    environment = load_json(run_dir / "environment.json")
    assert environment["libraries"]["scikit-learn"] == sklearn.__version__
    assert environment["cpu_count"] >= 1
    assert "git_revision" in environment and "git_dirty" in environment
    (run_dir / "models" / "linear_svm" / "bundle.joblib").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        load_completed_manifest(run_dir)
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "run_training or test_changes or transforms_test or input_changes or environment or invalid_run_id" -v`
Expected: FAIL vì orchestrator/CLI chưa tồn tại.

- [ ] **Step 3: Hiện thực orchestrator**

- `run_training` resolve đường dẫn theo `repo_root`; load + validate config; `validate_run_id`; nếu `output_root / run_id` đã tồn tại → `FileExistsError` trước mọi ghi. Tạo run dir, ghi `run_state.json` `running` nguyên tử.
- `verify_inputs` với `n_folds=config["n_folds"]`, `expected_intents`; chụp checksum đầu vào; `expand_candidates`; ghi `config.resolved.json` (config chuẩn hóa + danh sách candidate) và `environment.json`.
- Chạy `run_cross_validation` với callback ghi `fold_metrics.csv` nguyên tử sau mỗi fold; `summarize_fold_metrics(..., n_folds=config["n_folds"])`, `select_candidates`; ghi `candidate_summary.csv`, `selection.json`, lọc OOF theo `best_per_model` và ghi `oof_predictions.csv`; gọi `build_oof_reports`.
- `refit_final_models`, lưu từng bundle vào `models/<model-id>/bundle.joblib`, ghi `model_card.json`; smoke test load lại từng bundle và predict một instruction development.
- Tính lại checksum ba file dữ liệu và config; nếu khác ban đầu → `TrainingError` "input ... changed during run".
- Ghi `run_state.json` `completed`; tính `outputs` = hash mọi file trong run dir trừ `manifest.json`, khóa là relative POSIX path; ghi `manifest.json` cuối với `schema_version, run_id, status, created_at, completed_at, preparation {run_id, dataset_version, split_version, manifest_path, manifest_sha256}, seed, config_hash, inputs {preparation_manifest, cleaned_csv, split_assignments, split_report, config}, outputs, environment, selection`.
- Bọc toàn bộ sau khi tạo run dir trong `try/except`: khi lỗi ghi `run_state.json` `failed` kèm `error {type, message}`, không ghi manifest, rồi re-raise. Không tạo `--overwrite`.
- `capture_environment`: `sys.version`, `platform.platform/machine/processor`, `os.cpu_count()`, `importlib.metadata.version` cho `pandas,numpy,scikit-learn,scipy,joblib`, Git `rev-parse HEAD` + `status --porcelain` (null nếu lệnh thất bại), `captured_at` UTC.
- `load_completed_manifest`: đọc manifest, yêu cầu `status == "completed"`, kiểm tra từng `outputs` bằng `compute_sha256`, ném `ValueError("checksum mismatch: <rel>")` nếu sai.
- `main(argv=None)`: argparse với bốn tham số ở Interfaces; in run dir và winner; trả exit code 1 khi lỗi.

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "run_training or test_changes or transforms_test or input_changes or environment or invalid_run_id" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/run_training.py tests/unit/test_training.py
git commit -m "feat(training): orchestrate runs with manifest, environment, and atomic state"
```

---

### Task 9: Tài liệu, gitignore và nghiệm thu trên dữ liệu thật

**Files:**
- Create: `pipeline/training/README.md`
- Modify: `.gitignore`
- Modify: `pipeline/README.md`
- Test: `tests/unit/test_training.py`

**Interfaces:**
- Consumes: CLI Task 8.
- Produces: hướng dẫn chạy/đọc artifact, `/artifacts/training/` bị ignore, bằng chứng chạy thật.

- [ ] **Step 1: Viết test thất bại**

```python
def test_training_artifacts_are_gitignored():
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/artifacts/training/" in [line.strip() for line in ignored]
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py -k "gitignored" -v`
Expected: FAIL vì `.gitignore` chưa có mục này.

- [ ] **Step 3: Cập nhật gitignore và viết README**

- Thêm `/artifacts/training/` vào nhóm "Generated pipeline reports" trong `.gitignore`.
- `pipeline/training/README.md` ghi: lệnh CLI, ý nghĩa bốn tham số, cây artifact, hợp đồng bundle (`predict`, `decision_function`/`predict_proba` chỉ khi hỗ trợ), quy tắc chọn (mean Macro-F1, std, config order), test bị khóa, chạy tuần tự, lỗi hội tụ làm run failed, ý nghĩa `meets_cv_target=false` (run hoàn tất nhưng chưa đủ đề xuất release), cảnh báo không load joblib ngoài nguồn tin cậy.
- `pipeline/README.md`: đổi dòng `training/` và `configs/` từ "sắp tới" thành đã hiện thực; thêm mục chạy Training và mô tả artifact.

- [ ] **Step 4: Chạy toàn bộ test**

Run: `.\.venv\Scripts\pytest tests/unit/test_training.py tests/unit/test_preparation.py -v`
Expected: PASS toàn bộ, không hồi quy Preparation.

- [ ] **Step 5: Nghiệm thu trên dữ liệu thật**

Chọn run ID mới chưa tồn tại, ví dụ `03-11-2026-training-01`, rồi chạy:

```powershell
.\.venv\Scripts\python.exe -m pipeline.training.run_training `
  --preparation-manifest artifacts/preparation/03-11-2026-02/manifest.json `
  --config pipeline/configs/training.json `
  --run-id 03-11-2026-training-01
```

Ghi lại thời gian chạy và bộ nhớ quan sát (không đặt SLA). Kiểm tra bằng lệnh sau, thay run ID nếu khác:

```powershell
.\.venv\Scripts\python.exe -c "import json,pandas as pd; from pathlib import Path; r=Path('artifacts/training/03-11-2026-training-01'); m=json.load(open(r/'manifest.json',encoding='utf-8')); fm=pd.read_csv(r/'fold_metrics.csv'); cs=pd.read_csv(r/'candidate_summary.csv'); oof=pd.read_csv(r/'oof_predictions.csv'); print(m['status'], len(fm), len(cs), oof['model_id'].nunique(), oof.groupby(['model_id','sample_id']).size().max()); print(m['selection']['winner'], m['selection']['meets_cv_target'])"
```

Kỳ vọng: `completed 90 9 3 1`; winner thuộc ba candidate tốt nhất; `meets_cv_target` được ghi trung thực (có thể `False`). Nếu có `ConvergenceWarning`, run phải failed theo thiết kế: ghi nhận, tạo run ID mới sau khi xem xét cấu hình; không xóa cảnh báo, không sửa test.

- [ ] **Step 6: Commit**

```bash
git add .gitignore pipeline/training/README.md pipeline/README.md tests/unit/test_training.py
git commit -m "docs(training): document training pipeline and ignore generated artifacts"
```

---

## Ghi chú triển khai

- Chạy tuần tự mặc định; không thêm joblib/parallel hay orchestration framework. Nếu tối ưu song song sau này, phải giữ nguyên fold/lựa chọn và ghi mức song song + phần cứng vào manifest.
- `candidate_summary.csv` luôn có đủ candidate trong config, kể cả candidate không đủ fold (`eligible=false`), để không loại im lặng kết quả thấp.
- Selection chỉ dùng CV; test không tham gia bất kỳ phép tính nào. Mọi tuning tiếp theo sau khi xem test phải được công khai và test không còn là kiểm chứng độc lập cho vòng mới.
- Không cần tái hiện byte-identical giữa các máy; manifest + environment + hash là bằng chứng tái lập tương đối.


