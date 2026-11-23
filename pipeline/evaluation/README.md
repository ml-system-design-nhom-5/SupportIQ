# Subsystem Đánh giá (Evaluation) — SupportIQ

## Cập nhật sau review 8 vấn đề

- Dùng `data/benchmarks/system/v3/dev/suite_manifest.json` cho chẩn đoán. Bộ
  acceptance v3 có câu mới, pin dev/v1 để phát hiện normalized-text overlap và
  pin KB v2. Cả hai vẫn `draft`; người phụ trách cần duyệt gold/ngữ nghĩa trước
  khi chạy acceptance chính thức. Bộ v1/v2 chỉ giữ làm lịch sử.
- Runtime mặc định dùng `approved_kb.v2.json`. Test cần KB thiếu shipping phải
  chỉ rõ KB v1/fixture, không suy từ mặc định triển khai.
- Quality E2E live gửi vào endpoint nội bộ có nonce của managed process. Với
  dependencies giả lập, evaluator dùng `IsolatedCaller` và terminate/join process
  thực thi khi quá hạn; không tiêm ngoại lệ vào thread. Chuẩn bị worker ngoài
  phần execution deadline; không coi tổng thời gian mock setup là HTTP latency.
- `ml/releases/cv_metrics.json` khóa checksum release và báo cáo CV; importer
  kiểm tra artifact, đúng model/release, 10 fold và tính lại mean. Đây là kiểm tra
  nhất quán local, không phải chữ ký approval hay chạy lại training.
- Snapshot sanitized prompt + policy/order facts được ghi ở `llm_inputs` trước
  egress và trong kết quả run. Người chấm xem đúng snapshot/hash, không truy vấn
  một đơn hàng đã thay đổi để thay bằng chứng của lần chạy trước.
- Human annotation bắt buộc `reviewer_type: human`, reviewer, `reviewed_at` có
  timezone, `attestation.all_factual_claims_reviewed: true` (boolean) và relevance.
  Claim supported cần claim_text/source_id (hoặc citation)/doc_id/version/
  evidence_span. Phiếu cũ không tự được bổ sung chữ ký hoặc metadata giả.

```powershell
.venv\Scripts\python.exe -m pipeline.evaluation.run_system_evaluation --suite data/benchmarks/system/v3/dev/suite_manifest.json --config pipeline/configs/system_evaluation.dev.json --profile mock
```

Thành phần `pipeline/evaluation/` thực thi đánh giá độc lập các mô hình phân loại intent đã được huấn luyện và khóa lựa chọn từ giai đoạn Training:
1. **Hold-out Test Evaluation:** Đánh giá trên tập kiểm tra độc lập (6.690 mẫu chưa từng nhìn thấy trong lúc fit đặc trưng hoặc huấn luyện).
2. **Robustness Evaluation:** Đánh giá độ bền vững trước các nhiễu thực tế (casing, typos, negation, out-of-scope).
3. **Inference Latency & Throughput Benchmark:** Đo lường thời gian suy luận batch=1 (p50, p90, p95, p99) và thông lượng batch=256 trên CPU.
4. **Requirements Matrix & Provenance:** Xuất bảng đối chiếu yêu cầu sản phẩm và phả hệ nguồn gốc `manifest.json`.

---

## 1. Hướng dẫn Chạy CLI

Lệnh chạy đánh giá mô hình ML từ gốc repository:

```powershell
python -m pipeline.evaluation.run_evaluation `
  --mode ml `
  --training-manifest artifacts/training/03-11-2026-00/manifest.json `
  --config pipeline/configs/evaluation.json `
  --run-id 03-11-2026-00 `
  --output-root artifacts/evaluation
```

### Ý nghĩa các tham số:
- `--mode`: Chế độ đánh giá (`ml` hoặc `system`). Ở phiên bản hiện tại, chế độ `ml` đánh giá các mô hình phân loại intent. Chế độ `system` sẽ được bổ sung theo kế hoạch System Evaluation.
- `--training-manifest`: Đường dẫn tới file `manifest.json` của lần chạy Training đã hoàn tất (bắt buộc khi `--mode=ml`).
- `--suite`: (Tùy chọn) Đường dẫn tới bộ kịch bản kiểm thử độ bền vững (`suite_manifest.json`). Nếu bỏ trống, kết quả robustness sẽ được ghi nhận là `not_evaluated`.
- `--config`: Đường dẫn tới file cấu hình đánh giá (mặc định `pipeline/configs/evaluation.json`).
- `--run-id`: Định danh run ID dạng `<ngày>-<tháng>-<năm>-<stt>` (ví dụ `03-11-2026-00`). Nếu không truyền, hệ thống tự động sinh ID tiếp theo qua `get_next_id`.
- `--output-root`: Thư mục gốc lưu trữ kết quả (mặc định `artifacts/evaluation`).

---

## 2. Cấu trúc Artifacts Đầu ra

Mỗi lần chạy đánh giá hoàn tất lưu toàn bộ kết quả tại `artifacts/evaluation/<run-id>/`:

```text
artifacts/evaluation/<evaluation-run-id>/
├── config.resolved.json         # Cấu hình đánh giá đã chuẩn hóa
├── environment.json             # Thông tin môi trường, phần cứng, Git commit, phiên bản thư viện
├── intent/<model-id>/           # Kết quả chi tiết của từng baseline model
│   ├── predictions.csv          # Dự đoán trên tập hold-out test (sample_id, y_true, y_pred)
│   ├── metrics.json             # Test Macro-F1, Accuracy, Weighted-F1, capability, core metrics
│   ├── per_class.csv            # Precision, Recall, F1, Support cho toàn bộ 46 intent
│   ├── confusion_matrix.csv     # Ma trận nhầm lẫn 46x46
│   ├── robustness.csv           # Thống kê độ chính xác theo từng lát cắt (slices)
│   └── latency.json             # Phân bố độ trễ (p50, p90, p95, p99) và thông lượng (items/s)
├── baseline_comparison.csv      # Bảng so sánh tổng hợp giữa các baseline (CV F1 vs Test F1, latency)
├── requirements_matrix.csv      # Bảng đối soát từng tiêu chuẩn đề bài (ML vs System)
├── report.md                    # Báo cáo tổng hợp định dạng Markdown
├── run_state.json               # Trạng thái tiến trình (running / completed / failed)
└── manifest.json                # Phả hệ nguồn gốc, hash đầu vào, hash toàn bộ artifact đầu ra
```

---

## 3. Các Nguyên tắc và Ràng buộc Cốt lõi

1. **Khóa Mô hình Chiến thắng (Winner Immutability):**
   - Mô hình chiến thắng (`winner`) được cố định từ kết quả 10-fold Cross-Validation trong giai đoạn Training.
   - Điểm số trên tập test chỉ dùng để báo cáo kiểm chứng độc lập; **tuyệt đối không được đổi winner dựa trên kết quả test**.
2. **Không Rò rỉ Dữ liệu (No Leakage):**
   - Khâu Evaluation chỉ gọi phương thức `predict` của `bundle.joblib`. Tuyệt đối không gọi `fit` hay `fit_transform`.
   - Không tinh chỉnh siêu tham số hay ngưỡng quyết định trên tập hold-out test.
3. **Phân định rõ ML vs System Scope:**
   - Đánh giá ML chỉ kết luận các chỉ tiêu liên quan đến mô hình phân loại intent (`ML Quality`, `ML Robustness`).
   - Các tiêu chí cấp hệ thống (Retrieval Recall@3, LLM Grounding, Oversight/Safety, End-to-End Latency) được ghi rõ trạng thái `not_evaluated` trong `requirements_matrix.csv` và không tự tiện đánh dấu `pass`.

---

## 4. Benchmark So sánh 5 Mô hình (Transformers vs Baselines)

Phân hệ mở rộng cho phép đối soát hiệu năng và chất lượng giữa ba baseline cổ điển (`linear_svm`, `logistic_regression`, `multinomial_nb`) cùng hai Transformer classifier DistilBERT (`distilbert-supportiq`, `supportpilot-distilbert`).

### Lệnh chạy CLI:

```powershell
python -m pipeline.evaluation.run_comparison `
  --config pipeline/configs/comparison.json `
  --output-root artifacts/evaluation
```

### Các nguyên tắc quản trị và kiểm soát provenance:
1. **Phân định Hold-out Độc lập vs Điểm số Mô tả:**
   - Ba baseline cổ điển sở hữu nguồn gốc phân chia dữ liệu độc lập (`independence_status: verified`, `eligible_for_independent_ranking: true`).
   - Hai mô hình Transformer (`distilbert-supportiq` là local fine-tuned trên 9.200 mẫu không qua 10-fold CV; `supportpilot-distilbert` là external fine-tuned) chưa có bằng chứng kiểm định sample membership tách biệt với tập test Bitext (`independence_status: unverified`, `eligible_for_independent_ranking: false`). Điểm số của chúng chỉ mang tính chất **mô tả**, không được xếp hạng vượt baseline hold-out.
2. **Khóa Winner Bất biến:**
   - Mô hình chiến thắng (`linear_svm`) từ 10-fold CV vẫn được giữ nguyên vẹn; điểm test của bất kỳ mô hình Transformer nào cũng không thay đổi winner.
3. **Chuẩn hóa Đo lường Hiệu năng Phần cứng (CPU Latency & Throughput):**
   - Cả 5 mô hình đều được benchmark trên cùng một giao thức đo tuần tự CPU: batch=1, warm-up 20 request, 1.000 requests đo lường, thread count được khóa qua cấu hình (`num_threads`).
   - Thời gian đo bao gồm tokenizer/preprocessor và forward pass của mô hình, không tính thời gian load weights.
   - Độ trễ của Transformer trên CPU (~15–30 ms) tự nhiên cao hơn so với mô hình tuyến tính TF-IDF (~0.5 ms) do độ phức tạp tính toán self-attention nhiều lớp.

---

## 5. Kiến trúc Đánh giá và Phân định Ranh giới Hệ thống

Nhằm đảm bảo nguyên tắc kiến trúc và tính độc lập của pipeline học máy, phân hệ `pipeline/evaluation/` tập trung hoàn toàn vào **Đánh giá Offline Mô hình Học máy (Model-centric Offline Evaluation)**:
- **`evaluate_intent.py`**: Đánh giá chất lượng phân loại Intent (Macro-F1, Accuracy, confusion matrix, slice metrics, robustness).
- **`evaluate_retrieval.py`**: Đánh giá chất lượng truy xuất (MRR, Hit@k, Precision@k, Recall@k).
- **`benchmark.py`**: Đo lường thông lượng (throughput) và độ trễ (latency percentiles p50, p90, p95, p99).
- **`run_comparison.py`**: So sánh mô hình baseline và Transformer, báo cáo benchmark offline.
- **`reporting.py`**: Xuất báo cáo Markdown và ma trận yêu cầu.
- **`run_evaluation.py`**: CLI điều phối đánh giá ML offline (`--mode ml`).

### Phân định Ranh giới Kiểm thử:
1. **Pipeline ML (`pipeline/evaluation/`)**: Chịu trách nhiệm đánh giá offline chất lượng mô hình trên artifact và bộ dữ liệu benchmark, không phụ thuộc và không khởi chạy backend ứng dụng.
2. **Backend Integration Tests (`backend/tests/integration/`)**: Chịu trách nhiệm kiểm thử tích hợp nghiệp vụ, cơ sở dữ liệu PostgreSQL, luồng xử lý ticket, worker leasing, guardrails an toàn, và bảo mật quyền hạn (156 test files).
3. **Local Deployment Verification (`deploy/local/tests/`)**: Chịu trách nhiệm kiểm thử runtime HTTP và kiểm tra sức khỏe hệ thống cục bộ (`test-local-run.sh`, `smoke-check.sh`).
4. **Loại bỏ `apps/` và Legacy System Harnesses**: Thư mục `apps/` và các harness đánh giá hệ thống cũ phụ thuộc vào nó đã được dỡ bỏ hoàn toàn, chấm dứt nợ kỹ thuật của ADR-0028.
