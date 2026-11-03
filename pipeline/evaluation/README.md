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
