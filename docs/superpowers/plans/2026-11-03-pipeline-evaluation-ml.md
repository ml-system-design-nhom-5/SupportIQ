# Evaluation ML Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đánh giá ba baseline đã khóa trên test/robustness và xuất benchmark có provenance, không huấn luyện lại hoặc thay winner.

**Architecture:** Bộ chấm ML đọc các bundle và manifest Training, xác minh lineage, suy luận trên cùng test và tổng hợp metrics. Hạ tầng cấu hình/report được dùng lại bởi [kế hoạch System](2026-11-03-pipeline-evaluation-system.md); ML hoàn chỉnh vẫn chạy độc lập và không ghi System pass.

**Tech Stack:** Python trong `.venv`, pandas, numpy, scikit-learn, joblib, pytest; không thêm dependency.

**Spec:** [Đặc tả Evaluation](../specs/2026-11-03-pipeline-evaluation-design.md). Yêu cầu “Lập kế hoạch luôn” cho phép lập kế hoạch theo các đề xuất trong spec, chưa phải lệnh hiện thực hoặc chạy benchmark cuối.

## Global Constraints

* 46 intent; 12 core intent lấy từ `pipeline.preparation.utils`; `partition="train"` nghĩa là development, `partition="test"` có `fold=-1`.
* Training chọn bằng 10-fold CV; mục tiêu Macro-F1 ≥ 0,85 là CV, không tự đặt ngưỡng test.
* Không gọi fit/fit_transform, không calibration, không chọn ngưỡng, không đổi winner theo test; không ghi đè Training hoặc Preparation.
* Chỉ load joblib tin cậy sau xác minh hash; run ID mới, không overwrite; completed manifest ghi cuối.
* Metrics 46 lớp dùng `zero_division=0`; 12 intent tính từ toàn bộ dự đoán 46 lớp.
* Latency CPU mặc định: batch=1, 20 warm-up, ít nhất 1.000 request; throughput riêng batch=256.
* Artifact dưới `artifacts/evaluation/<run-id>/`, đã được `.gitignore` bỏ qua. Chỉ commit code, cấu hình và fixture tổng hợp.
* Không sửa `docs/CHỦ ĐỀ 1.md`. Không phát sinh traffic trả phí hoặc giao dịch thật.

## Review Focus

1. Manifest chuyển từ máy khác có đường dẫn tuyệt đối cũ: lỗi rõ ràng, không tự chọn file cùng tên — Task 1.
2. Bundle wrapper luôn có predict_proba nhưng SVM không hỗ trợ: không gắn nhãn probability sai — Task 2.
3. Classifier trả thiếu nhãn, nhãn lạ hoặc không đủ số prediction: dừng, không cắt/loại mẫu — Task 2.
4. Ngắt giữa ghi report và manifest: run không completed, thư mục cũ không bị dùng lại — Task 4.
5. Test nhìn thấy trong CV hoặc suite thay đổi khi chạy: từ chối hoặc phát hiện hash thay đổi — Tasks 1, 3, 4.

## File map và giao diện chung

| File | Trách nhiệm |
| --- | --- |
| `pipeline/evaluation/__init__.py` | `EvaluationError(Exception)` |
| `pipeline/evaluation/contracts.py` | Config, schema đầu vào và xác minh manifest/split/bundle paths; thêm file này để runner không phình to |
| `pipeline/evaluation/evaluate_intent.py` | Metrics test và robustness, không I/O mô hình |
| `pipeline/evaluation/benchmark.py` | Timing có clock injection, sau đó System bổ sung timing/cost |
| `pipeline/evaluation/reporting.py` | Atomic writes, requirements matrix, report và manifest |
| `pipeline/evaluation/run_evaluation.py` | CLI và orchestration ML; System bổ sung nhánh sau |
| `pipeline/configs/evaluation.json` | Schema version, seed=42, labels/metrics, timing protocol |
| `tests/unit/test_evaluation_ml.py` | Fixture tổng hợp và kiểm thử các hợp đồng trên |
| `pipeline/evaluation/README.md` | Cách chạy và cách đọc báo cáo |

Định nghĩa trong `contracts.py`:

* `VerifiedMLInputs` dataclass: `training_manifest: dict`, `selection: dict`, `test: pd.DataFrame`, `class_order: list[str]`, `model_dirs: dict[str, Path]`, `input_hashes: dict[str, str]`, `source_paths: dict[str, Path]`.
* `load_config(path: Path) -> dict`; `verify_ml_inputs(training_manifest: Path, repo_root: Path, config: dict) -> VerifiedMLInputs`.
* `load_suite(path: Path, repo_root: Path, mode: str) -> dict`: trả suite manifest có key `robustness_cases: list[dict]` hoặc System cases tương ứng, `input_hashes`, `source_paths` đã resolve; kiểm tra schema/hash, không tự tạo gold.
* `hash_inputs(paths: dict[str, Path]) -> dict[str, str]`; `validate_run_id(run_id: str) -> None`: tên một thành phần đường dẫn, chặn absolute/traversal/cả hai loại slash.

### Task 1: Config và xác minh đầu vào

**Files:** Create `pipeline/evaluation/__init__.py`, `contracts.py`, `pipeline/configs/evaluation.json`, `tests/unit/test_evaluation_ml.py`.

**Interfaces:** Sử dụng `compute_sha256`, `STANDARD_INTENTS`, `CORE_PRODUCT_INTENTS`, `get_near_duplicate_key` từ preparation utils. Sản xuất các API contracts kể trên. Taxonomy/fold có tham số fixture nhỏ qua config test nội bộ; CLI chính thức vẫn 46 lớp/10 fold, không cung cấp cờ bỏ quality gate.

- [ ] **1. RED:** Viết `test_verify_inputs_checks_lineage_and_one_to_one_join`: fixture Training/Preparation có hash thật trong tmp_path; valid fixture trả đúng test IDs, `set(result.test.sample_id) == expected_test_ids`. Parametrize ID dư/thiếu/trùng, mismatch hash, missing file, run failed, card metric/target sai, winner sai và group crossing; tất cả `raises(EvaluationError)` với tên nguồn lỗi.
- [ ] **2. Chạy RED:** `python -m pytest tests/unit/test_evaluation_ml.py -k 'verify_inputs or config' --basetemp=.pytest-eval-ml-task1 -q`; kỳ vọng import/API thiếu làm fail. Dùng Python `.venv`; `--basetemp` là thư mục chuyên test, pytest có quyền xóa nội dung.
- [ ] **3. Implement:** Xác minh trước deserialize: hash toàn input cần dùng và bundles/cards, schema/status, bản selection file khớp manifest, model card metric và target theo từng best entry. Join với `validate="one_to_one"`, ID sets bằng nhau; kiểm tra taxonomy, test fold, 10 development folds và đủ lớp, group không giao/mâu thuẫn. Sai absolute path báo lỗi kèm nguồn, không fallback. Config reject unknown keys, số âm/NaN, warmup<0, requests<1000 hoặc batch không hợp lệ ở profile chính thức. `load_suite` kiểm tra case ID duy nhất, slice/gold/action hợp lệ, hash và split development/final đã khóa.
- [ ] **4. GREEN:** Chạy lại lệnh bước 2; tất cả case hợp lệ pass, sai bị từ chối. Test `test_missing_old_absolute_path_does_not_find_same_basename` và `test_run_id_rejects_path_escape` phải pass.
- [ ] **5. Commit checkpoint:** `git add pipeline/evaluation/__init__.py pipeline/evaluation/contracts.py pipeline/configs/evaluation.json tests/unit/test_evaluation_ml.py`; `git commit -m "feat: validate evaluation inputs and configuration"` khi người thực thi được phép commit, chỉ stage file của task.

### Task 2: Metrics và suy luận hold-out

**Files:** Create `pipeline/evaluation/evaluate_intent.py`; extend `tests/unit/test_evaluation_ml.py`.

**Interfaces:** `predict_rows(bundle: IntentModelBundle, rows: pd.DataFrame, batch_size: int) -> pd.DataFrame` trả `sample_id,y_true,y_pred`; `classification_report_data(predictions: pd.DataFrame, class_order: list[str], core_intents: list[str]) -> dict` trả `metrics`, `per_class` DataFrame, `confusion_matrix` DataFrame và `core_metrics`. Chỉ gọi `bundle.predict`; score optional không bắt buộc cho metrics.

- [ ] **1. RED:** Viết `test_core_precision_keeps_false_positives_from_other_labels`: gold `[A,B]`, pred `[A,A]`, core `[A]` cho precision A=0.5, recall=1, F1=2/3; confusion true rows/pred columns là `[[1,0],[1,0]]`. Viết `test_predict_uses_bundle_without_fit` gắn spy fit/fit_transform ném AssertionError; nhãn test đủ thứ tự ID qua nhiều batch. Parametrize short output, label ngoài class_order, NaN prediction -> EvaluationError.
- [ ] **2. Chạy RED:** `python -m pytest tests/unit/test_evaluation_ml.py -k 'precision or predict or score_capability' --basetemp=.pytest-eval-ml-task2 -q` -> fail do API chưa có.
- [ ] **3. Implement:** Dùng sklearn metrics với labels fixed và zero_division=0; không sort hoặc drop mẫu âm thầm. Chuẩn hóa score columns theo `bundle.classes_` nếu xuất score; `score_kind` lấy capability classifier, không dùng hasattr(wrapper). SVM không predict_proba; lỗi suy luận khác không được biến thành unsupported.
- [ ] **4. GREEN:** Chạy lại bước 2. Thêm `test_svm_score_capability_is_margin_not_probability` và `test_bundle_class_order_maps_scores` với thứ tự lớp đảo; pass. Không cần xuất score nếu policy chưa dùng, nhưng capability phải trung thực trong report.
- [ ] **5. Commit checkpoint:** Stage hai file task, `git commit -m "feat: evaluate locked intent models on holdout data"`.

### Task 3: Robustness và timing classifier

**Files:** Extend `evaluate_intent.py`; create `benchmark.py`; extend unit test.

**Interfaces:** `evaluate_robustness(bundle: IntentModelBundle, cases: list[dict], class_order: list[str]) -> dict`; `benchmark_classifier(bundle: IntentModelBundle, texts: list[str], config: dict, clock: Callable[[], float] = time.perf_counter) -> dict`.

- [ ] **1. RED:** `test_robustness_separates_known_noncore_and_ood`: known noncore có gold hợp lệ và tính correctness; OOD/multi-intent null gold không vào F1 46 lớp, action detection `unsupported` khi chỉ có classifier. `test_paired_robustness_denominator` kiểm tra conditional correctness mẫu số chỉ những câu gốc đúng, zero denominator -> null. `test_timing_excludes_warmup_and_counts_requests` dùng fake clock, warmup=2/requests=4 trong fixture, assert 6 calls nhưng percentile chỉ 4 số đo đã biết.
- [ ] **2. Chạy RED:** `python -m pytest tests/unit/test_evaluation_ml.py -k 'robustness or timing' --basetemp=.pytest-eval-ml-task3 -q` -> fail API.
- [ ] **3. Implement:** Slice report gồm support, accuracy và paired stats theo source ID đã xác minh; không tạo ngưỡng phát hiện OOD từ test score. Latency quanh predict gồm transformer, không load; throughput batch=256 riêng, warmup không vào percentile. Ghi số mẫu duy nhất, số lặp, thread/CPU, clock và unit seconds. Runtime prediction error làm ML run fail; không loại mẫu. Suite hash trước/sau được runner kiểm tra.
- [ ] **4. GREEN:** Lệnh bước 2 pass. Thêm `test_empty_latency_input_rejected`, `test_latency_requires_nonnegative_finite_durations`, `test_robustness_missing_source_id_rejected`; pass.
- [ ] **5. Commit checkpoint:** Stage file task, `git commit -m "feat: add intent robustness and inference benchmark"`.

### Task 4: Runner, báo cáo và trạng thái requirements

**Files:** Create `run_evaluation.py`, `reporting.py`; extend tests.

**Interfaces:** `run_ml_evaluation(training_manifest: Path, suite: Path | None, config: dict, run_id: str, repo_root: Path, output_root: Path) -> dict`; `write_reports(run_dir: Path, results: dict, metadata: dict) -> dict[str, Path]`; `build_requirements_matrix(results: dict, mode: str) -> pd.DataFrame`. Reuse atomic writers từ Training nếu phù hợp, không sửa Training. ML suite optional để chạy hold-out độc lập; thiếu suite thì robustness `not_evaluated`, không pass. Đây là chi tiết làm rõ CLI trong spec.

- [ ] **1. RED:** `test_ml_runner_keeps_cv_winner_when_test_ranking_changes`: fixture predict cho NB thắng test nhưng selection winner SVM; assert winner vẫn SVM và comparison có cả hai hàng. `test_ml_only_does_not_pass_system_requirements`: mọi yêu cầu retrieval/LLM/safety/end-to-end là not_evaluated. `test_failed_run_has_no_completed_manifest`, `test_existing_run_is_not_modified`, `test_input_changed_midrun_fails`.
- [ ] **2. Chạy RED:** `python -m pytest tests/unit/test_evaluation_ml.py -k 'runner or requirements or completed or existing_run or midrun' --basetemp=.pytest-eval-ml-task4 -q` -> fail API.
- [ ] **3. Implement:** Reserve run dir `exist_ok=False`, ghi running; validate và load bundle; chạy Tasks 2–3; nhập CV metrics theo từng model; xuất đúng artifacts theo spec. Trạng thái từng metric reported/pass/fail/not_evaluated/unsupported khác run status. CV target theo từng model, test F1 reported. Report nêu winner locked, test đã mở, dữ liệu tổng hợp và giới hạn group heuristic. Hash trước/sau, atomic writes; completed manifest cuối, output hashes loại chính manifest. Exception -> failed state và raise EvaluationError, không cập nhật artifacts cũ.
- [ ] **4. GREEN:** Lệnh bước 2 pass. Test report chết giữa ghi file bằng monkeypatch writer phải không có completed manifest. Quyền ghi/thư mục đầy -> lỗi có tên artifact, không log instruction/PII hàng loạt.
- [ ] **5. Commit checkpoint:** Stage file task, `git commit -m "feat: orchestrate versioned ML evaluation reports"`.

### Task 5: CLI, hướng dẫn và smoke test tích hợp

**Files:** Extend runner/tests; create `pipeline/evaluation/README.md`; modify `pipeline/README.md` mục evaluation.

**Interfaces:** `main(argv: list[str] | None = None) -> int`: mode ml, training-manifest, optional suite, config, run-id, output-root default artifacts/evaluation; root từ repo chứ không thư mục script. System mode được thêm theo kế hoạch tiếp theo; trước đó mode system phải báo chưa hỗ trợ rõ ràng, không giả tạo thành công.

- [ ] **1. RED:** `test_cli_ml_end_to_end_writes_reloadable_report` dùng fixture bundle nhỏ serialized qua API thật; assert predictions đúng IDs, mọi output hash đọc lại khớp, completed, system not_evaluated. `test_cli_reports_failure_exit_code` exit !=0 khi hash sai; `test_run_from_directory_with_spaces` chạy từ đường dẫn khác với repo_root mapping tường minh.
- [ ] **2. Chạy RED:** `python -m pytest tests/unit/test_evaluation_ml.py -k 'cli or directory_with_spaces' --basetemp=.pytest-eval-ml-task5 -q` -> fail thiếu main/CLI.
- [ ] **3. Implement:** CLI argparse và README PowerShell một dòng; giải thích 3 metrics CV/test/robustness, file input, scope ML-only, test exposure, thư mục tạm dành riêng. Không ghi spec là đã có số liệu test. README link đặc tả/kế hoạch System. `--help` không load model hoặc chạy benchmark.
- [ ] **4. GREEN:** Chạy lại bước 2; sau đó `python -m pytest tests/unit/test_preparation.py tests/unit/test_training.py tests/unit/test_evaluation_ml.py --basetemp=.pytest-eval-ml-regression -q` và `git diff --check`. Kỳ vọng mọi test được thu thập đều pass, không chỉ gọi hàm trực tiếp. Chỉ rerun sau lỗi/thay đổi có liên quan.
- [ ] **5. Commit checkpoint:** Stage đúng file task, `git commit -m "docs: document and verify ML evaluation workflow"`.

## Chạy benchmark cuối và bàn giao

- [ ] Trước mở test: người phụ trách xác nhận Training và selection đã chốt, checksum hợp lệ, số test đúng assignments. Các run benchmark cũ phải được ghi nhận, không gọi dữ liệu đã dùng tuning là hold-out mới.
- [ ] Có thể chạy hold-out từ Training manifest hiện có mà không cần suite: `python -m pipeline.evaluation.run_evaluation --mode ml --training-manifest artifacts/training/03-11-2026-00/manifest.json --config pipeline/configs/evaluation.json --run-id <new-run-id>`.
- [ ] Nếu suite robustness chưa có, dừng ở báo cáo hold-out với `not_evaluated`; không chế tác final suite từ lỗi test rồi khẳng định độc lập. Người phụ trách tạo/duyệt suite theo spec rồi chạy ID mới, ghi rõ thứ tự đánh giá.
- [ ] Bàn giao report, manifest, test/robustness support, benchmark CPU và limitations. Đây là đánh giá mô hình ứng viên, chưa cho phép release toàn hệ thống.

## Self-review kế hoạch

Các mục 2–4, 7 (classifier), 9–11 của spec được phủ bởi Tasks 1–5; retrieval/LLM/guardrails/end-to-end/product value nằm trong kế hoạch System. Mọi API được định nghĩa trong File map hoặc task sở hữu; unit fixture nhỏ không làm giảm ràng buộc production. Năm Review Focus đều có test chỉ định. Không thay đổi dữ liệu, code Training hoặc đề bài trong kế hoạch này.
