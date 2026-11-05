# Subsystem Đánh giá (Evaluation) — SupportIQ

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

## 5. Đánh giá Toàn hệ thống (System Evaluation)

Phân hệ đo lường và thẩm định chất lượng toàn chuỗi: **ML Classifier -> Intake Gate Routing -> Semantic Retrieval -> Google AI Studio -> Human Oversight**.

### 5.1. Hai Profile Chạy (`mock` vs `live`)

1. **`mock` (Mặc định):**
   - Chạy offline hoàn toàn, không yêu cầu mạng, không đọc API key.
   - Thẩm định orchestration, xử lý lỗi có kiểm soát (fault scenarios), session ownership, và tính bất biến của artifacts.
   - Báo cáo mang nhãn `evidence_kind: simulated`. Kết quả exit code là `2` vì dữ liệu giả lập không thể chứng nhận đạt tiêu chuẩn nghiệm thu live.
2. **`live` (Acceptance chính thức):**
   - Đi qua classifier `supportiq_distilbert` trên ML inference service được ghim (pinned endpoint), BGE encoder thật với weights local, và Google AI Studio Gemini API.
   - Bắt buộc kiểm tra preflight: kiểm tra release mô hình, tính sẵn sàng của encoder, snapshot tri thức, và ngân sách token (`BudgetLedger`).
   - Yêu cầu cấu hình explicit API key qua biến môi trường server-side, không fallback vector giả hoặc template soạn sẵn.

### 5.2. Lệnh Chạy CLI

```powershell
# Chạy đánh giá toàn hệ thống (Mock Profile offline)
python -m pipeline.evaluation.run_evaluation `
  --mode system `
  --profile mock `
  --suite data/benchmarks/system/v1/suite_manifest.json `
  --config pipeline/configs/system_evaluation.json `
  --run-id system-mock-001 `
  --output-root artifacts/evaluation

# Nhập kết quả chấm thủ công (Human Assessment)
python -m pipeline.evaluation.assess_system `
  --run-dir artifacts/evaluation/system-mock-001 `
  --annotations tests/fixtures/system_evaluation/example_annotations.jsonl `
  --assessment-id review-001 `
  --product-sessions tests/fixtures/system_evaluation/example_product_sessions.csv
```

### 5.3. Ý nghĩa Mã thoát (Exit Codes)

- **`0`**: Tất cả các cổng chất lượng bắt buộc (`mandatory_gates`) đều đạt chuẩn với bằng chứng live hợp lệ.
- **`2`**: Quá trình đánh giá hoàn tất hợp lệ nhưng chưa đạt chuẩn nghiệm thu (hoặc chạy trên profile `mock` chỉ có bằng chứng giả lập, hoặc thiếu bằng chứng con người).
- **`1`**: Lỗi cấu hình, vi phạm phả hệ provenance (checksum mismatch), vi phạm đường dẫn thoát repository, hoặc sự cố preflight hạ tầng.

### 5.4. Live thử nghiệm khi suite chưa được duyệt

Dùng `pipeline/configs/system_evaluation.experimental.json` với
`allow_draft_suite: true` để chạy dữ liệu draft mà không thay trạng thái phê duyệt.
Kết quả mang nhãn `live_experimental`, luôn chưa được chứng nhận nghiệm thu.
Cấu hình mặc định vẫn từ chối live acceptance với suite draft.

`ml/releases/manifest.json` ghi checksum của sáu artifact local của
`supportiq_distilbert`; weights/tokenizer được đối chiếu với release mà ML service
đang pin. Cần chạy ML service ở `127.0.0.1:8001`, kiểm tra `/ready`, và có encoder
được cache trước. API key chỉ nằm trong biến môi trường hoặc `.env` phía server.

Chạy từ gốc repo bằng PowerShell (đổi run ID cho mỗi lần chạy):

```powershell
@'
from dotenv import load_dotenv
from pipeline.evaluation.run_system_evaluation import main
load_dotenv('.env', override=False)
raise SystemExit(main([
    '--profile', 'live',
    '--suite', 'data/benchmarks/system/v1/suite_manifest.json',
    '--config', 'pipeline/configs/system_evaluation.experimental.json',
    '--run-id', 'system-live-experimental-001'
]))
'@ | .venv\Scripts\python.exe -X utf8 -
```

Các lần chạy live mới đo latency qua `POST /api/demo/runs` của demo server riêng,
với cùng snapshot/config/as-of và ledger của run. Timer `api_total` bao gồm HTTP,
middleware, xử lý backend, persistence và serialization; không gồm tải model,
browser rendering hoặc thời gian người duyệt. Lưu từng mẫu trong
`latency_results.jsonl`; timeout/lỗi vẫn có record trong tập đo.

Để bổ sung HTTP latency cho run cũ mà không chạy lại 156 case hoặc ghi đè báo cáo:

```powershell
.venv\Scripts\python.exe -m pipeline.evaluation.complete_system_report `
  --parent-run artifacts/evaluation/05-11-2026-system-live-experimental-00 `
  --output-dir artifacts/evaluation/05-11-2026-system-http-assessment-01
```

Lệnh này dùng suite và experimental config hiện tại, kiểm tra checksum của run
gốc trước/sau đo, trừ số call/chi phí dự phòng đã dùng khỏi ngân sách 200 call/
1 USD của thử nghiệm. Thư mục đầu ra phải mới. Các input đã thay đổi cần được
đánh giá như một thử nghiệm khác, không coi là cùng lần chạy cũ.

Grounding vẫn cần annotation của người chấm; chế độ thử nghiệm không tự tạo
bằng chứng phê duyệt hoặc bỏ qua kiểm tra checksum. Phiếu sơ bộ AI được ghi
`reviewer_type: ai` và không được import như điểm chấm thủ công. Người duyệt đọc
`grounding/review.md`, điền danh tính/thời điểm, kiểm tra từng claim/evidence và
cập nhật `grounding/human_review.jsonl` trước khi dùng `assess_system`.
Những case kỳ vọng có draft nhưng chưa tạo được vẫn là thiếu bằng chứng, kể cả
khi mọi draft đã có đều được duyệt.
