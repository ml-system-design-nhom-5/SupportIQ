# Transformer và Baseline Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đánh giá hai classifier DistilBERT có sẵn cùng ba baseline trên cùng tập câu hỏi, xuất bảng so sánh có kiểm soát provenance, nguy cơ trùng dữ liệu và điều kiện phần cứng.

**Architecture:** Giữ nguyên benchmark baseline cũ; thêm adapter Transformer và runner comparison riêng dùng lại metrics/robustness của Evaluation. Benchmark chất lượng dùng test IDs cố định; baseline lịch sử được nhập sau xác minh hash, latency năm model được đo lại cùng giao thức CPU trong run mới. Model bên ngoài có overlap chưa xác minh vẫn có thể chấm điểm mô tả nhưng không được xếp như kết quả hold-out độc lập.

**Tech Stack:** Python `.venv`, pandas/numpy/scikit-learn hiện có; PyTorch/Transformers/tokenizers/safetensors cho suy luận local. Không huấn luyện mới, tải lại weights hoặc gọi API trả phí trong kế hoạch này.

**Spec:** [Đặc tả Evaluation](../specs/2026-11-03-pipeline-evaluation-design.md), [kế hoạch ML](2026-11-03-pipeline-evaluation-ml.md). Kế hoạch này bổ sung hợp đồng so sánh Transformer; không sửa mô hình, đề bài hoặc baseline winner đã khóa.

## Global Constraints

* Taxonomy cố định 46 intent và phân tích 12 core intent; score columns phải ánh xạ theo `id2label`, không theo vị trí tùy ý.
* Không fit/finetune/calibrate, không thay winner CV theo test; không ghi đè benchmark hoặc artifacts Training cũ.
* Dùng `local_files_only=True`, `trust_remote_code=False`, weights safetensors; thiếu file/label mapping sai phải lỗi, không tự tạo classification head ngẫu nhiên.
* Thiết bị chất lượng mặc định CPU/FP32, `model.eval()` và `torch.inference_mode()`. Không tự giảm precision hoặc fallback từ CUDA sang CPU mà không ghi rõ.
* Latency CPU: batch=1, warm-up20, requests1000; throughput batch256, cùng thứ tự texts giữa cả năm model. Đo tokenizer và model, không gồm load; CPU thread count được khóa bằng config và ghi vào manifest.
* Run ID mới, SHA-256 đầu vào/đầu ra, completed manifest cuối; lỗi model/provenance không được âm thầm bỏ dòng so sánh.

## 1. Hiện trạng đã kiểm tra

| Đối tượng | Vị trí | Nhận định |
| --- | --- | --- |
| External fine-tuned | `artifacts/models/finetuned/supportpilot-distilbert/` | Có config, tokenizer và weights; nguồn dự kiến `abdulmuinnn/supportpilot-distilbert`, cần xác minh revision/checksum. Chưa có bằng chứng split huấn luyện không trùng test SupportIQ. |
| Local trained | `artifacts/models/trained/distilbert-supportiq/` | `training_report.json` ghi model nền local pretrained, train9200, validation1840, epochs2, batch32, lr3e-5; không có sample IDs/checksum dữ liệu trong report hiện có. |
| Pretrained | `artifacts/models/pretrained/distilbert-base-uncased/` | Model nền, chưa có head phân loại 46 intent đã học; chỉ làm provenance, không thêm thành classifier thứ sáu. |
| Baselines | `artifacts/training/03-11-2026-00/` | NB, LR và SVM đã refit; giữ selection và winner CV. |
| Benchmark có sẵn | `artifacts/evaluation/03-11-2026-00/` | Có manifest, predictions và bảng điểm test của ba baseline; không có suite tại `data/evaluation/` lúc kiểm tra. |

Model `trained` của dự án là **local fine-tuned**, không phải Transformer huấn luyện từ đầu. Script `pipeline/training/train_distilbert.py` nạp pretrained, lấy mẫu chỉ từ partition train rồi chia train/validation riêng. Đây là bằng chứng code hiện tại; chưa đủ chứng minh artifacts hiện có được tạo từ đúng snapshot/ID dữ liệu đó. Điểm validation trong report không phải 10-fold CV và không so trực tiếp với CV baseline.

Điểm test baseline hiện có, chỉ để đối soát (không hard-code làm expected production): NB0.983645, LR0.990113, SVM0.991591 Macro-F1. Report cũ có test6690 theo Preparation liên quan; runner phải lấy số thật từ assignments và checksums.

## Review Focus

1. Config HF thiếu nhãn hoặc có `LABEL_0`: từ chối, không suy mapping theo sort tên nhãn — Task2.
2. Historical benchmark dùng split/model khác: dừng import, không ghép các điểm khác tập test — Task1.
3. Local training snapshot không chứng minh độc lập test: gắn provenance chưa xác minh, không xếp hạng kết quả độc lập — Tasks1/4.
4. External fine-tuned có thể thấy Bitext test: điểm chỉ mô tả; không tuyên bố vượt baseline độc lập — Task4.
5. CUDA timing bất đồng bộ hoặc fallback/OOM: synchronize đúng, lỗi rõ, không trộn latency CPU/GPU — Task3.

## 2. Files và giao diện

Create:

* `pipeline/evaluation/comparison_contracts.py`: config, registry, kiểm tra provenance và historical report.
* `pipeline/evaluation/transformer_adapter.py`: tokenizer/model load local và API predict tương thích.
* `pipeline/evaluation/run_comparison.py`: runner riêng, CLI, bảng/report.
* `pipeline/configs/comparison.json`: đường dẫn hai Transformer, baseline manifests, max_length, thiết bị, threads và timing.
* `tests/unit/test_model_comparison.py`: unit/smoke fixture; không tải model thật trong test.

Modify `pipeline/evaluation/benchmark.py` chỉ khi cần timing hooks dùng chung; giữ API `benchmark_classifier()` tương thích. Bổ sung `pipeline/evaluation/README.md` cho luồng comparison và requirements Transformer riêng tại `pipeline/requirements-transformers.txt`. Không sửa bundle/classifier Training.

## Task 1: Khóa đầu vào, baseline lịch sử và provenance registry

**Interfaces:** `verify_comparison_inputs(config: dict, repo_root: Path) -> dict` trả verified test DataFrame, `class_order`, `baseline_model_dirs`, `transformer_specs`, `historical_results`, `source_paths`, `input_hashes`. Dùng lại `verify_ml_inputs()` để xác minh baseline Training và test; historical manifest phải completed và hashes khớp.

- [x] **RED:** Viết `test_historical_test_ids_match_exactly`: historical predictions khác/thiếu/trùng IDs -> EvaluationError; matching IDs nhưng y_true khác -> error. Viết `test_model_and_split_hashes_must_match_history`: hash bundle/cleaned/split khác -> error. `test_missing_provenance_is_explicit_not_verified`: không có sample membership evidence thì registry.status=`unverified`, không tạo chứng nhận.
- [x] **Run RED:** `python -m pytest tests/unit/test_model_comparison.py -k 'historical or provenance' --basetemp=.pytest-compare-task1 -q` -> fail API thiếu.
- [x] **Implement:** Config nhận đúng năm model IDs `multinomial_nb`, `logistic_regression`, `linear_svm`, `supportiq_distilbert`, `supportpilot_distilbert`; hash config/tokenizer/weights/report của Transformer. Kiểm tra historical manifest outputs và predictions theo model/candidate ID; không deserialize khi thiếu checksum baseline. Paths registry không cho escape artifact root. Ghi explicit nguồn và trạng thái evidence, không suy theo tên thư mục.
- [x] **GREEN:** Chạy lại lệnh; test source file đổi và manifest không completed đều fail có thông báo đúng. Số điểm historical có thể nhập, nhưng không nhập latency làm điểm đo hiện tại.
- [x] **Commit checkpoint:** Stage file task và commit `feat: verify comparison inputs and historical benchmark` nếu execution có quyền commit.

**Provenance trước chạy chính thức:** Chụp hash scripts/configs hiện có, report và weights. Nếu có saved train/val IDs thực của local model thì kiểm tra giao với test bằng sample ID và near key. Nếu không có, tái dựng từ script+seed chỉ là evidence hỗ trợ, không được trình bày là lịch sử đã xác minh. Muốn chuyển status verified cần bổ sung record đáng tin hoặc huấn luyện run mới có membership manifest trong công việc riêng; không retrain tự động ở Evaluation. External model cũng cần bằng chứng membership/revision để xác minh. Không có thì vẫn chạy chế độ mô tả với warning bắt buộc.

## Task 2: Adapter Transformer không huấn luyện

**Interfaces:** `TransformerIntentAdapter(model_dir: Path, model_id: str, max_length: int = 64, device: str = "cpu")`, `.classes_: list[str]`, `.predict(texts: Sequence[str]) -> np.ndarray`, `.predict_proba(texts) -> np.ndarray`, `.synchronize() -> None`. Dùng lại `predict_rows`, `classification_report_data`, `evaluate_robustness`; chỉnh type hints theo structural interface nếu cần, không yêu cầu subclass sklearn bundle.

- [x] **RED:** `test_adapter_maps_reordered_hf_labels`: fake logits argmax1 phải ra label của id2label1, không lấy alphabetic1. Parametrize LABEL_n, thiếu nhãn, nhãn lặp, logits sai chiều -> EvaluationError. `test_inference_never_initializes_random_head`: mock loader kiểm tra thiếu classifier weights -> error thay vì warning rồi tiếp tục. `test_adapter_uses_eval_inference_and_local_files` assert không training/gradient/network.
- [x] **Run RED:** `python -m pytest tests/unit/test_model_comparison.py -k adapter --basetemp=.pytest-compare-task2 -q` -> fail module.
- [x] **Implement:** AutoTokenizer/AutoModelForSequenceClassification load strict local; kiểm tra architecture, id2label/label2id bijection46 lớp, loading_info không thiếu classifier weights. Tokenize truncation max_length64, padding theo batch và attention_mask; không thêm near-key punctuation preprocessing vào model HF. Dùng tokenizer đã lưu và khai báo input preprocessing trong registry. Không tự dùng prompt/response. Return đúng số prediction và taxonomy, kiểm tra finite logits. max_length64 cho cả hai là protocol đề xuất, ghi truncation count; nếu có evidence model yêu cầu khác, tách profile và báo khác biệt.
- [x] **GREEN:** Lệnh trên pass; `test_empty_input_returns_empty_without_model_call`, `test_fullwidth_input_handling_is_declared`, `test_probability_columns_match_classes` pass. Transformer không bắt buộc NFKC như TF-IDF; không đổi preprocessing đã học chỉ để so cùng chuỗi normalized.
- [x] **Commit checkpoint:** Stage file task, commit `feat: add local transformer evaluation adapter`.

## Task 3: Benchmark năm mô hình trên cùng phần cứng

**Interfaces:** Giữ `benchmark_classifier(bundle,texts,config,clock=...)`; thêm optional synchronization callback hoặc adapter hook bao quanh timing ở warm-up/latency/throughput, không thay hành vi sklearn. Config CPU threads gồm torch và BLAS/threadpoolctl nếu có sẵn; dùng thư viện phụ thuộc sklearn, không giả `cpu_count` là số threads thực.

- [x] **RED:** `test_latency_protocol_is_identical_for_all_models`: cùng ordered IDs, requests1000/warmup20/batch1/tp256; fake clock assert tokenizer nằm trong timing và load ngoài. `test_gpu_sync_brackets_timed_prediction`: synchronize trước start/sau predict. `test_no_silent_cpu_fallback`: CUDA unavailable/OOM -> lỗi run/profile, không gắn nhãn GPU cho CPU result.
- [x] **Run RED:** `python -m pytest tests/unit/test_model_comparison.py -k 'latency or gpu or fallback' --basetemp=.pytest-compare-task3 -q` -> fail hooks mới.
- [x] **Implement:** CPU là bảng latency chính cho cả năm model, ghi precision, device, threads, warmup, text count/length, model load seconds, model file size. Ghi thời gian lặp và p50/p95 ms; throughput đo cùng số batch lặp được config khóa, không so một batch GPU với nhiều batch CPU. CUDA là profile bổ sung chỉ khi user muốn, ghi GPU name/VRAM và synchronize; không dùng điểm latency GPU để xếp lẫn CPU. Thread changes scoped/restore. Không chạy1.000 request bằng cách coi một batch1.000 là1.000 latency mẫu.
- [x] **GREEN:** Lệnh trên và regression benchmark cũ pass. Unit dùng requests nhỏ; config chính thức vẫn1000. Kiểm tra zero/NaN/negative duration error, không xuất throughput infinity.
- [x] **Commit checkpoint:** Stage file task, commit `feat: benchmark comparable CPU and optional GPU inference`.

## Task 4: Runner, bảng điểm và phân loại tính độc lập

**Interfaces:** `run_comparison(config_path: Path, run_id: str | None, repo_root: Path, output_root: Path = Path("artifacts/evaluation")) -> dict`; `main(argv: list[str] | None = None) -> int`.

- [x] **RED:** `test_comparison_has_five_rows_and_keeps_cv_winner`: model external test tốt nhất không đổi winner SVM. `test_external_score_is_descriptive_when_overlap_unknown`: row có `independence_status=unverified`, `eligible_for_independent_ranking=false`. `test_local_missing_cv_is_na_not_zero`: không gán final_val_macro_f1 thành CV. `test_new_run_does_not_modify_historical_artifacts` kiểm tra hashes trước/sau.
- [x] **Run RED:** `python -m pytest tests/unit/test_model_comparison.py -k 'comparison or score or missing_cv or historical_artifacts' --basetemp=.pytest-compare-task4 -q` -> fail runner.
- [x] **Implement:** Dùng Tasks1–3. Nhập metrics baseline từ predictions đã xác minh rồi tính lại theo taxonomy chung, đối soát numeric tolerance1e-9 với summary historical. Chấm hai Transformer cùng holdout IDs. Lưu source_mode imported/recomputed cho từng metric; baseline timing được đo lại. Không tạo winner mới; optional independent ranking chỉ gồm rows có membership evidence verified. Local subset9200 không cùng training budget với baseline37911, ghi training_samples/CV protocol riêng, không tuyên bố thuật toán tốt hơn chỉ vì bảng điểm.
- [x] **GREEN:** Tests trên pass; thêm test model load/predict thất bại, config/model/suite đổi giữa run -> failed không completed. Không loại model thất bại rồi báo so đủ năm.
- [x] **Commit checkpoint:** Stage file task, commit `feat: compare transformer classifiers with locked baselines`.

Artifacts trong run mới:

```text
artifacts/evaluation/<comparison-run-id>/
├── model_registry.json          # origin, hash, label/preprocessing/device, provenance status
├── comparison.csv               # 5 rows, metrics, history reference, independence flags
├── config.resolved.json
├── environment.json
├── intent/<model-id>/           # predictions, metrics, per_class, confusion, latency
├── robustness/<model-id>/       # chỉ khi có suite thật; thiếu ghi not_evaluated
├── report.md
├── run_state.json
└── manifest.json
```

Report phân nhóm **hold-out có evidence độc lập** và **kết quả mô tả/chưa xác minh overlap**, kèm cùng raw score khi có; không chỉ chú thích nhỏ rồi xếp tất cả như nhau. Pretrained chỉ xuất trong lineage, không tạo prediction với head ngẫu nhiên. Lưu prediction/model hash, test IDs hash, version của torch/transformers và source revisions nếu có.

## Task 5: Hướng dẫn, smoke test và chạy benchmark có kiểm soát

**Files:** `pipeline/evaluation/README.md`, `pipeline/requirements-transformers.txt`, comparison config, unit tests.

- [x] **RED:** `test_cli_comparison_offline_smoke` dùng fake local model/tokenizer và serialized fixture baseline thật; outputs đủ5 rows, hashes đọc lại đúng, không gọi fit/network. `test_config_device_and_unknown_keys_rejected` chặn giá trị không hỗ trợ, max_length<=0, threads<=0.
- [x] **Run RED:** `python -m pytest tests/unit/test_model_comparison.py -k 'cli or config' --basetemp=.pytest-compare-task5 -q` -> fail CLI/config.
- [x] **Implement:** CLI `python -m pipeline.evaluation.run_comparison --config pipeline/configs/comparison.json` tự sinh ID mới, optional --run-id/--output-root. Requirements Transformer ghi range tương thích sau kiểm tra `.venv`, không nâng toàn bộ môi trường tùy ý; không cần web research nếu chỉ dùng API đã có trong local training script. README nêu local model cũng fine-tuned, điều kiện import benchmark, ý nghĩa independence flags và chi phí CPU latency có thể lâu hơn baseline.
- [x] **GREEN:** Chạy test comparison rồi regression preparation/training/evaluation bằng `.venv\Scripts\python.exe -m pytest tests/unit --basetemp=.pytest-comparison-regression -q`; nếu unit suite có test ứng dụng khác cần service, chọn đúng các file pipeline và ghi danh sách. `git diff --check`; CLI --help phải không load weights hoặc chạy prediction. Không báo kết quả benchmark thật từ fixture.
- [x] **Commit checkpoint:** Commit đúng file task `docs: document five-model comparison workflow`.

## 3. Chạy thực tế và tiêu chí nghiệm thu

- [x] Xác minh artifacts/specs/input hashes trước khi chạy; phát hiện source Training hoặc model card chưa hợp lệ thì dừng để sửa nguồn, không bypass.
- [x] Tạo registry cho hai Transformer, công khai local report thiếu ID/checksums và external split unknown; giữ status unverified nếu chưa bổ sung evidence đáng tin.
- [x] Chạy CPU comparison bằng run ID mới, giữ nguyên historical baseline benchmark. Không chạy GPU bổ sung nếu chưa cần; không chọn model mới chỉ từ điểm test.
- [x] Nếu chưa có robustness suite độc lập đã duyệt, report `not_evaluated`. Nếu cần kiểm chứng external thực sự độc lập, chuẩn bị bộ câu hỏi mới không lấy từ Bitext theo quy trình đánh giá riêng, không coi việc khử exact duplicate là đủ chứng minh unseen.
- [x] Đối soát baseline test scores với benchmark cũ, test IDs bằng nhau; mọi khác biệt phải có nguyên nhân trước công bố. Latency có thể khác vì đo lại, phải báo môi trường/threads mới.
- [x] Bàn giao bảng5 models, per-class/confusion, 12-intent metrics, timings CPU, giới hạn training budget/provenance và manifest. Không chỉnh artifacts model hoặc hoàn tất release trong công việc này.

## Self-review

Phủ metrics/taxonomy/hold-out từ spec Evaluation qua Tasks1/2/4; latency và GPU synchronization Task3; provenance, lỗi/phiên bản Task1/4; hướng dẫn/regression Task5. Các mục retrieval/LLM/human oversight không thuộc yêu cầu so sánh classifier này. Năm Review Focus có test xác định, không viết benchmark scores giả, không phát sinh retraining hoặc nâng cấp model để đạt số liệu.
