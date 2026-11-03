# Pipeline học máy của SupportIQ

Hệ thống pipeline học máy của SupportIQ được thiết kế và hiện thực hóa dựa trên các nguyên lý kỹ nghệ trong sách **Machine Learning in Production: From Models to Systems** (trích xuất từ `ai-for-production.zip`), đặc biệt là:
- **Chương 11 — Automating the ML Pipeline:** Cấu trúc phân đoạn (staged pipeline), tránh phản mẫu *pipeline jungle* và *big-ass script architecture*, tự động hóa điều phối quy trình (workflow orchestration).
- **Chương 16 — Data Quality:** Đảm bảo 5 chiều chất lượng dữ liệu (Accuracy, Completeness, Uniqueness, Consistency, Currentness), Data Linting, Data Schemas và khám phá trực quan (EDA).
- **Chương 17 — Pipeline Quality:** Khử lỗi tiềm ẩn (silent mistakes), kiểm thử thành phần độc lập (unit testing), và cam kết **No Data Leakage** (chống rò rỉ dữ liệu).
- **Chương 24 — Versioning, Provenance, and Reproducibility:** Quản lý phiên bản dữ liệu và artifact bất biến (`DD-MM-YYYY-stt`), truy vết phả hệ nguồn gốc qua `manifest.json` và mã băm SHA-256.

---

## 1. Cấu trúc Tổng thể

```text
pipeline/
├── requirements.txt            # Quản lý phụ thuộc (pandas, scikit-learn, joblib, matplotlib)
├── README.md                   # Hướng dẫn chi tiết & đối chiếu lý thuyết
├── preparation/                # GIAI ĐOẠN ĐÃ HOÀN THIỆN: Khảo sát, làm sạch, chia tập, đặc trưng
│   ├── __init__.py
│   ├── utils.py                # Sinh ID DD-MM-YYYY-stt, SHA-256, I/O JSON, chuẩn hóa Unicode NFKC
│   ├── inspect_data.py         # Khảo sát dữ liệu khám phá (EDA) & xuất đồ thị trực quan
│   ├── validate_data.py        # Kiểm tra schema, giá trị thiếu, danh mục nhãn & xung đột trùng lặp
│   ├── clean_data.py           # Làm sạch text, bảo toàn {{...}}, cách ly mẫu lỗi (quarantined)
│   ├── split_data.py           # Chia tập Test & 10-Fold CV (StratifiedGroupKFold - No Leakage)
│   ├── features.py             # Bộ biến đổi TF-IDF (fit độc lập trên train, xuất joblib)
│   └── run_preparation.py      # Bộ điều phối (Runner) thực thi liên hoàn end-to-end
├── training/                   # GIAI ĐOẠN ĐÃ HOÀN THIỆN: 10-Fold CV 3 baseline, refit, bundles
│   ├── __init__.py
│   ├── models.py               # Config schema, validation, và factory estimator
│   ├── cross_validate.py       # Vòng lặp CV 10 fold, tie-break, OOF, refit
│   ├── artifacts.py            # Bundle suy luận, model card, ghi file nguyên tử
│   ├── run_training.py         # Điều phối training, xác minh hợp đồng, manifest
│   └── README.md               # Chi tiết hợp đồng và hướng dẫn chạy
├── configs/                    # File cấu hình thí nghiệm
│   └── training.json           # Grid 3 baseline, 10 fold, TF-IDF params, target 0.85
├── evaluation/                 # Đánh giá hold-out test và robustness suite (sắp tới)
├── deployment/                 # Đóng gói và phát hành gói model (sắp tới)
└── monitoring/                 # Theo dõi suy luận, drift và phân tích chất lượng (sắp tới)
```

---

## 2. Đối chiếu Nguyên lý từ `ai-for-production.zip`

| Nguyên lý trong sách | Chương | Hiện thực hóa trong SupportIQ |
|---|---|---|
| **Staged & Modular Pipeline** | Ch. 11 | Chia nhỏ thành các module đơn trách nhiệm (`inspect`, `validate`, `clean`, `split`, `features`), có CLI độc lập và runner điều phối chung (`run_preparation.py`). |
| **Exploratory Data Analysis (EDA)** | Ch. 16 | `inspect_data.py` phân tích độ dài ký tự/từ (min, max, mean, percentiles p90, p95, p99), thống kê 46 intent, xuất biểu đồ `figures/class_distribution.png`, `length_distribution.png`, `category_intent_matrix.png`. |
| **Data Schema & Taxonomy Linting** | Ch. 16 | `validate_data.py` kiểm tra schema bắt buộc, xác thực 46 intent và 13 category chuẩn của Bitext, bắt các chuỗi rỗng/whitespace. |
| **Detecting Contradictions & Quarantine** | Ch. 16 & 17 | `clean_data.py` phát hiện các câu hỏi trùng lặp text nhưng mang nhãn intent mâu thuẫn (`conflicting_labels_across_duplicates`) và cách ly toàn bộ vào `quarantined.csv` kèm lý do rõ ràng. |
| **Silent Mistakes & Leakage Prevention** | Ch. 17 | `split_data.py` áp dụng `StratifiedGroupKFold` gom nhóm tất cả câu trùng/gần trùng vào cùng một fold/partition; assertion tự động xác nhận 0% giao thoa từ khóa giữa Train và Test. |
| **Safe Feature Transformation** | Ch. 11 & 17 | `features.py` không bao giờ fit trước trên toàn bộ dữ liệu. `IntentFeaturePipeline` chỉ fit trên tập train của từng fold/split, đồng thời giữ nguyên vẹn token entity `{{...}}`. |
| **Provenance, Lineage & Reproducibility** | Ch. 24 | Quy ước ID `<ngày>-<tháng>-<năm>-<stt>` (ví dụ `03-11-2026-00`), băm SHA-256 dữ liệu đầu vào và các artifact đầu ra, ghi nhận toàn bộ vào `manifest.json`. Cố định seed cho phân chia ngẫu nhiên. |

---

## 3. Quy ước Lưu trữ Dữ liệu và Artifacts

```text
data/datasets/
├── bitext-retail-ecommerce-llm-chatbot-training-dataset.csv (dữ liệu thô ban đầu)
├── processed/<dataset-version>/
│   ├── cleaned.csv             # Dữ liệu sạch đưa vào huấn luyện/đánh giá
│   └── quarantined.csv         # Dữ liệu bị cách ly kèm cột quarantine_reason
└── splits/<split-version>/
    └── split_assignments.csv   # Phân chia sample_id theo partition (train/test) và fold (0..9)

artifacts/
├── preparation/<run-id>/
│   ├── manifest.json           # Phả hệ nguồn gốc, hash SHA-256 và tham chiếu artifacts
│   ├── profile.json            # Hồ sơ thống kê tổng quan dataset
│   ├── class_distribution.csv  # Bảng tần suất và tỷ lệ % 46 intent
│   ├── validation_report.json  # Báo cáo kết quả kiểm tra chất lượng DQ-01 -> DQ-04
│   ├── review_candidates.csv   # Danh sách các mẫu cần người rà soát
│   ├── duplicate_groups.csv    # Bảng gom nhóm các câu hỏi trùng lặp
│   ├── cleaning_report.json    # Thống kê kết quả làm sạch và phân loại cách ly
│   ├── split_report.json       # Thống kê phân bố nhãn các fold và xác nhận 0% rò rỉ
│   └── figures/                # Thư mục biểu đồ trực quan hóa EDA
│       ├── class_distribution.png
│       ├── length_distribution.png
│       └── category_intent_matrix.png
└── models/<run-id>/
    └── tfidf.joblib            # Bộ trích xuất đặc trưng TF-IDF fit từ tập train
```

---

## 4. Hướng dẫn Chạy Pipeline

### 4.1. Cài đặt Môi trường
```bash
python -m pip install -r pipeline/requirements.txt
```

### 4.2. Chạy Từng Module Độc lập

- **Khảo sát dữ liệu (Inspect & EDA):**
  ```bash
  python -m pipeline.preparation.inspect_data --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv --output-dir artifacts/preparation/03-11-2026-00
  ```

- **Kiểm tra chất lượng (Validate):**
  ```bash
  python -m pipeline.preparation.validate_data --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv --output-dir artifacts/preparation/03-11-2026-00
  ```

- **Làm sạch & Cách ly (Clean):**
  ```bash
  python -m pipeline.preparation.clean_data --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv --processed-dir data/datasets/processed --report-dir artifacts/preparation/03-11-2026-00
  ```

- **Phân chia Test / 10-Fold CV (Split):**
  ```bash
  python -m pipeline.preparation.split_data --input data/datasets/processed/03-11-2026-00/cleaned.csv --splits-dir data/datasets/splits --report-dir artifacts/preparation/03-11-2026-00 --test-size 0.15 --n-splits 10
  ```

- **Fit & Lưu đặc trưng TF-IDF trên Train:**
  ```bash
  python -m pipeline.preparation.features --cleaned-csv data/datasets/processed/03-11-2026-00/cleaned.csv --splits-csv data/datasets/splits/03-11-2026-00/split_assignments.csv --output-dir artifacts/models --run-id 03-11-2026-00
  ```

### 4.3. Chạy Toàn bộ Pipeline Tự động (End-to-End Orchestrator)
Lệnh điều phối duy nhất tự động sinh ID ngày `DD-MM-YYYY-stt`, kết nối các khâu tuần tự và xuất `manifest.json`:
```bash
python -m pipeline.preparation.run_preparation --input data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv
```

### 4.4. Huấn luyện và So sánh Baseline (Training Orchestrator)
Thực thi 10-fold CV trên 3 thuật toán baseline (90 fold fits), tự động khóa winner, refit mô hình trên toàn development và xuất bundle suy luận:
```bash
python -m pipeline.training.run_training \
  --preparation-manifest artifacts/preparation/03-11-2026-02/manifest.json \
  --config pipeline/configs/training.json \
  --run-id 03-11-2026-00
```

### 4.5. Kiểm thử Tự động (Unit Tests)
```bash
pytest tests/unit/test_preparation.py tests/unit/test_training.py -v
```
*(Toàn bộ các unit tests kiểm tra data contract, no leakage, fold layout, tie-break, inference bundle, atomic manifest, và không rò rỉ test đều vượt qua 100%)*
