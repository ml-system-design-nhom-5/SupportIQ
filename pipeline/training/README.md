# Subsystem Huấn luyện Mô hình — SupportIQ

Thành phần `pipeline/training/` thực thi huấn luyện và lựa chọn giữa ba thuật toán baseline truyền thống cho bài toán Intent Classification (46 nhãn):
1. **MultinomialNB** (`alpha: [0.1, 0.5, 1.0]`)
2. **LogisticRegression** (`C: [0.1, 1.0, 10.0]`)
3. **LinearSVC** (`C: [0.1, 1.0, 10.0]`)

Hệ thống đánh giá qua 10-fold Cross-Validation không rò rỉ, khóa lựa chọn tự động bằng tiêu chí tiền định, sau đó tái huấn luyện (refit) trên toàn bộ development set để xuất gói mô hình (inference bundle) cho Evaluation.

---

## 1. Hướng dẫn Chạy CLI

Lệnh chạy điều phối huấn luyện từ gốc repository:

```powershell
python -m pipeline.training.run_training `
  --preparation-manifest artifacts/preparation/03-11-2026-02/manifest.json `
  --config pipeline/configs/training.json `
  --run-id 03-11-2026-00 `
  --output-root artifacts/training
```

### Ý nghĩa các tham số:
- `--preparation-manifest`: Đường dẫn tới file `manifest.json` của giai đoạn Preparation đã hoàn tất (chứa đường dẫn `cleaned.csv`, `split_assignments.csv`, `split_report.json` và mã băm SHA-256 đối chiếu).
- `--config`: Đường dẫn tới file cấu hình JSON của thí nghiệm (mặc định `pipeline/configs/training.json`).
- `--run-id`: Định danh run ID dạng `<ngày>-<tháng>-<năm>-<stt>` (ví dụ `03-11-2026-00`). Nếu không chỉ định, hệ thống tự động sinh ID kế tiếp bằng `get_next_id`. **Run ID là bất biến, không hỗ trợ ghi đè (`--overwrite`)** nhằm bảo vệ phả hệ nguồn gốc.
- `--output-root`: Thư mục gốc chứa các thư mục run (mặc định `artifacts/training`).

---

## 2. Cấu trúc Artifacts Đầu ra

Mỗi run hoàn tất lưu toàn bộ kết quả dưới `artifacts/training/<run-id>/`:

```text
artifacts/training/<run-id>/
├── config.resolved.json         # Cấu hình đã chuẩn hóa kèm danh sách candidate mở rộng
├── environment.json             # Thông tin OS, phần cứng, Git commit, phiên bản thư viện
├── fold_metrics.csv             # Metrics chi tiết từng fold (Macro-F1, Acc, Weighted-F1, thời gian)
├── candidate_summary.csv        # Tổng hợp mean và std (ddof=0) của toàn bộ candidate
├── selection.json               # Cấu hình tốt nhất từng mô hình, tie-break, và winner
├── oof_predictions.csv          # Dự đoán out-of-fold cho ba cấu hình tốt nhất
├── reports/<model-id>/          # Báo cáo đánh giá OOF
│   ├── per_class_metrics.csv    # Precision, Recall, F1, Support cho toàn bộ 46 intent
│   ├── confusion_matrix.csv     # Ma trận nhầm lẫn 46x46
│   ├── top_confusions.csv       # Top 20 cặp intent hay nhầm lẫn nhất
│   └── core_intent_metrics.json # Đánh giá riêng 12 intent trọng tâm của sản phẩm
├── models/<model-id>/           # Gói suy luận và thẻ mô hình
│   ├── bundle.joblib            # Transformer và classifier đã refit trên toàn development
│   └── model_card.json          # Thẻ mô hình, phạm vi sử dụng, giới hạn và cổng chất lượng
├── run_state.json               # Trạng thái tiến trình (running / completed / failed)
└── manifest.json                # Phả hệ nguồn gốc, hash đầu vào và toàn bộ artifact đầu ra
```

---

## 3. Quy ước và Hợp đồng Kỹ thuật

1. **Khóa Tập Kiểm tra (Hold-out Test Isolation):**
   - Dữ liệu `partition="test"` chỉ được đọc ở bước xác minh danh mục nhãn, nhóm câu hỏi và mã băm SHA-256.
   - Tuyệt đối không fit transformer, transform đặc trưng hay dự đoán nhãn trên tập test trong khâu Training.
2. **Chống Rò rỉ Đặc trưng giữa các Fold:**
   - Mỗi fold tạo một đối tượng `IntentFeaturePipeline` mới tinh, chỉ `fit_transform` trên tập train của fold đó.
   - Không tái sử dụng artifact `tfidf.joblib` từ Preparation cho CV.
3. **Quy tắc Tie-break Xác định:**
   - Ưu tiên 1: Mean Macro-F1 cao hơn (làm tròn 6 chữ số thập phân).
   - Ưu tiên 2: Std Macro-F1 nhỏ hơn (độ lệch chuẩn quần thể `ddof=0`, làm tròn 6 chữ số thập phân).
   - Ưu tiên 3: Thứ tự cấu hình xuất hiện trong file config (`config_order`).
4. **Hợp đồng Bundle Suy luận (`IntentModelBundle`):**
   - Cung cấp API `predict(texts)` nhận batch chuỗi văn bản và tự động chuẩn hóa Unicode NFKC + khoảng trắng trước khi dự đoán.
   - `decision_function(texts)` và `predict_proba(texts)` chỉ khả dụng khi estimator bên dưới hỗ trợ. Tuyệt đối không tạo xác suất giả định cho `LinearSVC`.
   - **Cảnh báo an ninh:** Chỉ deserialize `bundle.joblib` từ các thư mục artifact nội bộ tin cậy.
5. **Xử lý Cảnh báo và Lỗi:**
   - Khi gặp `ConvergenceWarning` hoặc giá trị metric NaN/Inf, tiến trình bị dừng ngay lập tức và đánh dấu `run_state="failed"`. Không xuất bản manifest hoàn tất cho run lỗi.
   - Nếu `meets_cv_target=false` (Macro-F1 trung bình < 0.85), run vẫn được lưu trung thực để phục vụ phân tích nhưng ghi rõ chưa đủ điều kiện đề xuất phát hành (release).
