# Hướng dẫn Sử dụng Pipeline Preparation — SupportIQ

Khâu **Preparation** chịu trách nhiệm: **Khảo sát (EDA) ➔ Kiểm định chất lượng ➔ Làm sạch & Cách ly lỗi ➔ Chia tập Train/Test 10-Fold (chống rò rỉ) ➔ Xây dựng bộ trích xuất đặc trưng TF-IDF**.

---

## 1. Thiết lập Môi trường

Trước khi chạy, kích hoạt môi trường ảo Python của dự án và cài đặt các phụ thuộc Data Science:

```bash
# Kích hoạt virtual environment (nếu chưa kích hoạt)
# Trên Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Cài đặt các thư viện cần thiết
python -m pip install -r pipeline/requirements.txt
```

---

## 2. Cách Chạy Nhanh Toàn Bộ Pipeline (Khuyến nghị)

Chỉ cần chạy **1 lệnh duy nhất** thông qua Orchestrator `run_preparation.py`. Hệ thống sẽ tự động:
1. Quét và sinh mã ID phiên bản theo định dạng `<ngày>-<tháng>-<năm>-<stt>` (ví dụ: `03-11-2026-00`, `03-11-2026-01`,...).
2. Thực thi liên hoàn: **Inspect ➔ Validate ➔ Clean ➔ Split ➔ Fit Features**.
3. Xuất toàn bộ artifacts và tổng hợp vào `manifest.json`.

```bash
python -m pipeline.preparation.run_preparation --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv
```

### Các tùy chọn nâng cao khi chạy toàn bộ:
```bash
python -m pipeline.preparation.run_preparation \
    --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv \
    --run-id 03-11-2026-00 \        # (Tùy chọn) Chỉ định ID cố định
    --test-size 0.15 \              # Tỷ lệ tập test (mặc định 15%)
    --n-splits 10 \                 # Số fold cross-validation (mặc định 10 folds)
    --seed 42                       # Random seed để tái lập kết quả
```

---

## 3. Cách Chạy Độc Lập Từng Module

Nếu muốn chạy riêng lẻ từng bước để thử nghiệm hoặc kiểm tra kết quả:

### Bước 1: Khảo sát & Trực quan hóa dữ liệu (EDA) — `inspect_data.py`
Đọc dữ liệu thô, thống kê độ dài câu hỏi, phân bố 46 intent và 13 category, đồng thời vẽ biểu đồ phân tích lưu vào thư mục `figures/`.

```bash
python -m pipeline.preparation.inspect_data \
    --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv \
    --output-dir artifacts/preparation/03-11-2026-00
```
* **Kết quả sinh ra:**
  * `profile.json`: Báo cáo thống kê độ dài ký tự/từ (min, max, mean, percentiles p90, p95, p99).
  * `class_distribution.csv`: Bảng tần suất và tỷ lệ % của 46 nhãn.
  * `figures/class_distribution.png`: Biểu đồ cột phân bố nhãn.
  * `figures/length_distribution.png`: Biểu đồ phân bố số từ trong câu hỏi.
  * `figures/category_intent_matrix.png`: Biểu đồ nhiệt quan hệ giữa Category và Intent.

---

### Bước 2: Kiểm định chất lượng dữ liệu — `validate_data.py`
Kiểm tra Schema bắt buộc, giá trị Null/rỗng, nhãn ngoài danh mục, phát hiện các câu trùng lặp hoàn toàn hoặc **mâu thuẫn nhãn** (cùng câu hỏi nhưng mang 2 intent khác nhau).

```bash
python -m pipeline.preparation.validate_data \
    --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv \
    --output-dir artifacts/preparation/03-11-2026-00
```
* **Kết quả sinh ra:**
  * `validation_report.json`: Báo cáo số lỗi theo từng tiêu chí kiểm định.
  * `review_candidates.csv`: Danh sách các mẫu lỗi/nghi ngờ lỗi kèm mã lý do (`issue_reasons`).
  * `duplicate_groups.csv`: Bảng gom nhóm các mẫu câu trùng lặp để theo dõi.

---

### Bước 3: Làm sạch & Cách ly dữ liệu — `clean_data.py`
Chuẩn hóa text theo Unicode NFKC, loại bỏ khoảng trắng thừa, bảo toàn các entity token `{{...}}`, cách ly các mẫu lỗi/mâu thuẫn nhãn vào `quarantined.csv`, loại bỏ trùng lặp và gán `sample_id` chuẩn.

```bash
python -m pipeline.preparation.clean_data \
    --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv \
    --processed-dir data/datasets/processed \
    --report-dir artifacts/preparation/03-11-2026-00 \
    --dataset-version 03-11-2026-00
```
* **Kết quả sinh ra:**
  * `data/datasets/processed/03-11-2026-00/cleaned.csv`: Dữ liệu sạch sẵn sàng để huấn luyện.
  * `data/datasets/processed/03-11-2026-00/quarantined.csv`: Các mẫu bị cách ly kèm lý do cụ thể.
  * `artifacts/preparation/03-11-2026-00/cleaning_report.json`: Thống kê số lượng ban đầu, số lượng làm sạch và lý do cách ly.

---

### Bước 4: Phân chia tập Test & 10-Fold CV chống rò rỉ — `split_data.py`
Chia Hold-out Test (15%) và 10 Fold Cross-Validation (85%). Áp dụng thuật toán `StratifiedGroupKFold` để **gom toàn bộ các câu hỏi trùng/gần trùng vào cùng 1 fold/tập test**, tuyệt đối không để rò rỉ (Zero Data Leakage).

```bash
python -m pipeline.preparation.split_data \
    --input data/datasets/processed/03-11-2026-00/cleaned.csv \
    --splits-dir data/datasets/splits \
    --report-dir artifacts/preparation/03-11-2026-00 \
    --split-version 03-11-2026-00 \
    --test-size 0.15 \
    --n-splits 10 \
    --seed 42
```
* **Kết quả sinh ra:**
  * `data/datasets/splits/03-11-2026-00/split_assignments.csv`: Danh sách `sample_id` kèm cột `partition` (`train`/`test`) và `fold` (`0..9` cho train, `-1` cho test).
  * `artifacts/preparation/03-11-2026-00/split_report.json`: Thống kê phân bố nhãn theo từng fold và xác nhận `leakage_detected: false`.

---

### Bước 5: Fit bộ trích xuất đặc trưng TF-IDF trên Train — `features.py`
Fit `IntentFeaturePipeline` **chỉ trên tập Train** (tránh rò rỉ), bảo toàn token `{{...}}`, và lưu file mô hình serialize `tfidf.joblib`.

```bash
python -m pipeline.preparation.features \
    --cleaned-csv data/datasets/processed/03-11-2026-00/cleaned.csv \
    --splits-csv data/datasets/splits/03-11-2026-00/split_assignments.csv \
    --output-dir artifacts/models \
    --run-id 03-11-2026-00 \
    --max-features 10000
```
* **Kết quả sinh ra:**
  * `artifacts/models/03-11-2026-00/tfidf.joblib`: Bộ biến đổi đã fit xong từ tập train.

---

## 4. Cách Lập trình & Tái sử dụng trong Code Huấn luyện (Python API)

Trong giai đoạn tiếp theo (`pipeline/training/`), chỉ cần import và sử dụng trực tiếp các class/module đã chuẩn hóa:

```python
import pandas as pd
from pipeline.preparation.features import IntentFeaturePipeline

# 1. Đọc dữ liệu đã xử lý và danh sách phân chia
df_clean = pd.read_csv("data/datasets/processed/03-11-2026-00/cleaned.csv")
df_splits = pd.read_csv("data/datasets/splits/03-11-2026-00/split_assignments.csv")
merged = df_clean.merge(df_splits, on="sample_id")

# 2. Lấy dữ liệu train cho Fold 0 (ví dụ)
train_fold0 = merged[(merged["partition"] == "train") & (merged["fold"] != 0)]
val_fold0   = merged[(merged["partition"] == "train") & (merged["fold"] == 0)]

# 3. Fit TF-IDF trên tập train của fold đó
feature_pipeline = IntentFeaturePipeline(max_features=10000, ngram_range=(1, 2))
X_train = feature_pipeline.fit_transform(train_fold0["instruction"])
X_val   = feature_pipeline.transform(val_fold0["instruction"])

# 4. Lưu lại transformer khi cần
feature_pipeline.save("artifacts/models/03-11-2026-00/tfidf_fold0.joblib")

# 5. Đọc lại transformer để suy luận (Inference):
loaded_pipeline = IntentFeaturePipeline.load("artifacts/models/03-11-2026-00/tfidf_fold0.joblib")
sample_matrix = loaded_pipeline.transform(["Where is my order {{Tracking Number}}?"])
```

---

## 5. Chạy Kiểm thử Tự động (Unit Tests)

Để bảo đảm toàn bộ hệ thống hoạt động chính xác trước khi commit hoặc trước khi huấn luyện mô hình:

```bash
# Chạy toàn bộ 13 unit tests
pytest tests/unit/test_preparation.py -v
```

Các bài test tự động bao gồm:
- Kiểm tra tính hợp lệ của gói thư viện Data Science.
- Kiểm tra cơ chế tự động tăng ID ngày (`DD-MM-YYYY-stt`).
- Kiểm tra tính toàn vẹn SHA-256 và I/O JSON.
- Kiểm tra bắt đúng các lỗi rỗng, thiếu trường, nhãn sai danh mục.
- Kiểm tra cách ly mẫu lỗi và mâu thuẫn nhãn vào `quarantined.csv`.
- Kiểm tra **không rò rỉ dữ liệu (No Data Leakage)** giữa các fold và tập test.
- Kiểm tra bộ biến đổi TF-IDF bảo toàn các entity placeholder `{{...}}`.
- Kiểm tra tích hợp liên hoàn end-to-end.
