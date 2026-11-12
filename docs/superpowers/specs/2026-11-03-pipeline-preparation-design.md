# Đặc tả thiết kế: Pipeline Chuẩn Bị Dữ Liệu & Đặc Trưng (Data Preparation & Features)

**Dự án:** SupportIQ — AI Customer Support Copilot for E-commerce  
**Ngày:** 03/11/2026  
**Trạng thái:** Đã thống nhất thiết kế (Approved)  
**Tác giả:** Nhóm phát triển SupportIQ & Claude  

---

## 1. Mục tiêu và Phạm vi

### 1.1. Mục tiêu
Hiện thực hóa module `pipeline/preparation/` hoàn chỉnh cho bài toán phân loại ý định (Single-label Intent Classification) trên tập dữ liệu Bitext E-commerce (46 intent, 13 category, trọng tâm 12 intent sản phẩm). 

Module đảm bảo:
- Thống kê, khảo sát dữ liệu khám phá (EDA) và xuất các biểu đồ trực quan.
- Kiểm tra tính hợp lệ dữ liệu (schema, thiếu sót, mâu thuẫn nhãn, trùng lặp).
- Chuẩn hóa văn bản, bảo toàn token placeholder thực thể `{{...}}`, cách ly mẫu lỗi vào `quarantined.csv`.
- Phân chia tập Development (Train 10-Fold CV) và Hold-out Test độc lập, gom nhóm các câu hỏi trùng/gần trùng để **ngăn ngừa rò rỉ dữ liệu (No Data Leakage)**.
- Xây dựng bộ biến đổi đặc trưng TF-IDF chuẩn scikit-learn (`fit`/`transform`), chỉ fit trên tập huấn luyện của từng fold/split.
- Tự động sinh và quản lý ID đồng bộ theo quy tắc `<ngày>-<tháng>-<năm>-<stt>` (ví dụ: `03-11-2026-00`).

### 1.2. Ranh giới (Boundaries)
- **Trong phạm vi:** 
  - Toàn bộ 5 file trong `pipeline/preparation/` (`inspect_data.py`, `validate_data.py`, `clean_data.py`, `split_data.py`, `features.py`) cùng `utils.py` và runner `run_preparation.py`.
  - Cấu hình phụ thuộc trong `pipeline/requirements.txt` (pandas, scikit-learn, joblib, matplotlib).
  - Quản lý các artifact sinh ra tại `data/datasets/` và `artifacts/preparation/`, `artifacts/models/`.
  - Bộ unit test kiểm thử toàn diện trong `tests/unit/test_preparation.py`.
- **Ngoài phạm vi:**
  - Huấn luyện mô hình phân loại (thuộc `pipeline/training/`).
  - Đánh giá mô hình cuối cùng (thuộc `pipeline/evaluation/`).
  - Dữ liệu tri thức chính sách và đơn hàng giả lập (`data/knowledge/`).

---

## 2. Quy ước Định danh (ID Convention) & Thư mục Lưu trữ

### 2.1. Quy ước Định danh ID
Tất cả các định danh (`run-id`, `dataset-version`, `split-version`) bắt buộc tuân theo quy chuẩn:
$$\text{DD-MM-YYYY-stt}$$
- Trong đó:
  - `DD`: Ngày hiện tại (2 chữ số, ví dụ `03`).
  - `MM`: Tháng hiện tại (2 chữ số, ví dụ `11`).
  - `YYYY`: Năm hiện tại (4 chữ số, ví dụ `2026`).
  - `stt`: Số thứ tự chạy trong ngày bắt đầu từ `00`, tiếp theo là `01`, `02`,...
- Module `utils.py` cung cấp hàm `get_next_id(base_dir, date_str=None)` để tự động quét thư mục và tăng số thứ tự tiếp theo nếu không được chỉ định tường minh.

### 2.2. Vị trí Lưu trữ Dữ liệu và Artifacts
```text
data/datasets/
├── bitext-retail-ecommerce-llm-chatbot-training-dataset.csv (nguồn thô ban đầu)
├── processed/<dataset-version>/
│   ├── cleaned.csv
│   └── quarantined.csv
└── splits/<split-version>/
    └── split_assignments.csv

artifacts/
├── preparation/<run-id>/
│   ├── manifest.json
│   ├── profile.json
│   ├── class_distribution.csv
│   ├── validation_report.json
│   ├── review_candidates.csv
│   ├── duplicate_groups.csv
│   ├── cleaning_report.json
│   ├── split_report.json
│   └── figures/
│       ├── class_distribution.png
│       ├── length_distribution.png
│       └── category_intent_matrix.png
└── models/<run-id>/
    └── tfidf.joblib
```

---

## 3. Thiết kế Kiến trúc Các Thành Phần

### 3.1. `pipeline/preparation/utils.py` (Common Utilities)
- **Chức năng:**
  - `get_next_id(base_dir: Path, date_str: str | None = None) -> str`: Quét thư mục, tìm số thứ tự lớn nhất trong ngày và trả về định danh `DD-MM-YYYY-stt`.
  - `compute_sha256(file_path: Path) -> str`: Tính toán mã băm SHA-256 phục vụ truy vết tính toàn vẹn (DQ-06).
  - `save_json(data: dict, file_path: Path)` & `load_json(file_path: Path) -> dict`: Đọc/ghi JSON định dạng chuẩn hóa, indent=2, UTF-8.
  - `create_manifest(...)`: Xuất `manifest.json` ghi nhận ngày giờ chạy, ID, hash dữ liệu đầu vào và các artifact đầu ra.

### 3.2. `pipeline/preparation/inspect_data.py` (Data Profiling & EDA)
- **Đầu vào:** File raw CSV (`instruction`, `intent`, `category`, `tags`, `response`).
- **Nghiệp vụ thực thi:**
  - Đọc và phân tích cấu trúc tổng thể: số dòng, số cột, kiểu dữ liệu, dung lượng bộ nhớ.
  - Thống kê phân bố nhãn: tần suất, tỷ lệ % cho 46 intent và 13 category.
  - Phân tích độ dài câu hỏi `instruction`: số ký tự và số từ (min, max, mean, median, p90, p95, p99).
  - Phân tích trường `tags` (các nhãn biến thể ngôn ngữ / loại câu).
  - Trực quan hóa dữ liệu và xuất đồ thị ra thư mục `figures/`:
    - `class_distribution.png`: Phân bố tần suất 46 intent (sắp xếp giảm dần).
    - `length_distribution.png`: Biểu đồ histogram & KDE về độ dài từ trong câu hỏi.
    - `category_intent_matrix.png`: Biểu đồ nhiệt (heatmap) hoặc ma trận quan hệ giữa category và intent.
- **Artifacts:**
  - `artifacts/preparation/<run-id>/profile.json`
  - `artifacts/preparation/<run-id>/class_distribution.csv`
  - `artifacts/preparation/<run-id>/figures/*.png`

### 3.3. `pipeline/preparation/validate_data.py` (Data Quality Assurance)
- **Đầu vào:** CSV dữ liệu (raw hoặc sau làm sạch).
- **Quy tắc kiểm tra (DQ-01 đến DQ-04):**
  - **Schema:** Bắt buộc có các cột `instruction`, `intent`, `category`.
  - **Completeness:** Không có giá trị NULL/NaN hoặc chuỗi rỗng trong `instruction` và `intent`.
  - **Validity:** `intent` phải nằm trong danh mục 46 intent chuẩn; `category` phải thuộc 13 category chuẩn.
  - **Uniqueness & Consistency:**
    - Phát hiện các bản ghi trùng lặp hoàn toàn (`instruction` và `intent` giống hệt).
    - Phát hiện các mẫu **mâu thuẫn nhãn**: cùng một `instruction` (sau khi chuẩn hóa khoảng trắng/chữ thường) nhưng mang hai nhãn `intent` khác nhau.
    - Đánh mã `duplicate_group_id` cho các câu trùng hoặc gần trùng.
- **Artifacts:**
  - `artifacts/preparation/<run-id>/validation_report.json`: Báo cáo số lượng đạt/vi phạm từng tiêu chí, tỷ lệ hợp lệ.
  - `artifacts/preparation/<run-id>/review_candidates.csv`: Danh sách các bản ghi lỗi hoặc nghi ngờ lỗi kèm lý do cụ thể.
  - `artifacts/preparation/<run-id>/duplicate_groups.csv`: Bảng gom nhóm các mẫu trùng hoặc mâu thuẫn nhãn.

### 3.4. `pipeline/preparation/clean_data.py` (Cleaning & Quarantine)
- **Đầu vào:** Raw CSV và thông tin từ bước Validate.
- **Nghiệp vụ thực thi:**
  - **Chuẩn hóa văn bản:** Chuẩn hóa Unicode (NFKC), loại bỏ khoảng trắng thừa đầu cuối và giữa các từ; giữ nguyên cấu trúc entity placeholder `{{...}}`.
  - **Cách ly mẫu lỗi (Quarantine):**
    - Mẫu thiếu `instruction` hoặc `intent` bị cách ly với lý do `missing_required_fields`.
    - Mẫu có `intent` ngoài 46 lớp bị cách ly với lý do `invalid_intent_label`.
    - Toàn bộ các câu thuộc nhóm **mâu thuẫn nhãn** (`conflicting_labels_across_duplicates`) được đưa vào danh sách cách ly, không tự ý chọn bừa một nhãn.
  - **Khử trùng lặp:** Đối với các câu trùng lặp hoàn toàn (cùng text, cùng nhãn), giữ lại 1 bản ghi đại diện duy nhất.
  - **Gán định danh mẫu:** Bổ sung cột `sample_id` (định dạng `sample_<index>` hoặc UUID ngắn) để thuận tiện truy vết.
- **Artifacts & Dữ liệu xuất:**
  - `data/datasets/processed/<dataset-version>/cleaned.csv`: Dữ liệu sạch đưa vào mô hình.
  - `data/datasets/processed/<dataset-version>/quarantined.csv`: Dữ liệu bị cách ly kèm cột `quarantine_reason`.
  - `artifacts/preparation/<run-id>/cleaning_report.json`: Thống kê số lượng ban đầu, số lượng làm sạch, số lượng cách ly theo từng lý do.

### 3.5. `pipeline/preparation/split_data.py` (Hold-out Test & 10-Fold Stratified Group CV)
- **Đầu vào:** `cleaned.csv`.
- **Nghiệp vụ phân chia và chống rò rỉ (Leakage Prevention):**
  - **Tách Hold-out Test set:** Cắt 15% tổng dữ liệu làm tập Test độc lập dùng để đánh giá cuối cùng.
  - **10-Fold CV trên Development set:** 85% còn lại được chia thành 10 fold đều nhau.
  - **Phân tầng (Stratified):** Đảm bảo tỷ lệ 46 intent đồng đều trên từng fold và tập test.
  - **Chống rò rỉ nhóm (Group Integrity):** Tất cả các câu hỏi có cùng `duplicate_group_id` (hoặc cùng nội dung văn bản chuẩn hóa) bắt buộc phải nằm **trong cùng một phân vùng** (cùng thuộc Test hoặc cùng thuộc 1 Fold cụ thể của Train). Không được để câu trong cùng nhóm xuất hiện ở cả Train và Test hay giữa các Fold chéo nhau.
  - **Kiểm tra rò rỉ tự động (Leakage Assertion):** Hàm kiểm tra quét giao giữa tập từ khóa/n-gram/text của Test và Train. Nếu tỷ lệ trùng lặp nhóm > 0%, script sẽ raise exception và hủy tiến trình.
- **Artifacts & Dữ liệu xuất:**
  - `data/datasets/splits/<split-version>/split_assignments.csv`: Chứa các cột `sample_id`, `partition` (`train` / `test`), `fold` (`0..9` đối với train, `-1` đối với test).
  - `artifacts/preparation/<run-id>/split_report.json`: Tỷ lệ mẫu theo nhãn trên từng fold, xác nhận kiểm tra 0% rò rỉ.

### 3.6. `pipeline/preparation/features.py` (TF-IDF Feature Extractor)
- **Đầu vào:** Dòng văn bản `instruction`.
- **Cấu trúc lớp `IntentFeaturePipeline`:**
  - Kế thừa hoặc bọc `sklearn.feature_extraction.text.TfidfVectorizer`.
  - Cấu hình chuẩn hóa:
    - `ngram_range=(1, 2)` (Unigram và Bigram).
    - `token_pattern=r"(?u)\b\w+\b|\{\{[^}]+\}\}"` (giữ nguyên vẹn các token placeholder như `{{Order History}}`).
    - `sublinear_tf=True`, `min_df=2`, `max_features=10000`.
  - Cung cấp các phương thức:
    - `fit(texts: Iterable[str]) -> IntentFeaturePipeline`
    - `transform(texts: Iterable[str]) -> scipy.sparse.csr_matrix`
    - `fit_transform(texts: Iterable[str]) -> scipy.sparse.csr_matrix`
    - `save(path: str | Path)` & `classmethod load(path: str | Path)` dùng `joblib`.
  - **Quy tắc an toàn tuyệt đối:** Extractor chỉ được fit trên tập train của từng fold/split. Không fit trước trên toàn bộ dataset nhằm tránh data leakage.
  - Tích hợp CLI cho phép kiểm thử fit trên tập train của một split-version cụ thể và lưu thử nghiệm `tfidf.joblib`.

### 3.7. `pipeline/preparation/run_preparation.py` (End-to-End Orchestrator)
- Cung cấp một điểm chạy tập trung:
  1. Tự động sinh ID duy nhất `DD-MM-YYYY-stt` (dùng chung cho `run-id`, `dataset-version`, `split-version`).
  2. Lần lượt chạy tuần tự: `inspect` -> `validate` -> `clean` -> `split` -> `test fit features`.
  3. Tổng hợp toàn bộ metadata, thông số, đường dẫn và checksum vào `artifacts/preparation/<run-id>/manifest.json`.

---

## 4. Kế hoạch Kiểm thử & Tiêu chuẩn Nghiệm thu (Verification & Acceptance Criteria)

### 4.1. Unit Tests (`tests/unit/test_preparation.py`)
- `test_id_generation`: Kiểm tra hàm sinh ID tự động tăng `00`, `01`, `02` đúng regex `\d{2}-\d{2}-\d{4}-\d{2}`.
- `test_validation_catches_invalid_data`: Đưa vào dữ liệu giả lập có null, intent lạ, câu mâu thuẫn nhãn -> xác minh báo cáo và danh sách cách ly bắt đúng 100%.
- `test_clean_data_quarantine`: Xác nhận mẫu lỗi bị đưa vào `quarantined.csv`, mẫu sạch đưa vào `cleaned.csv`, placeholder `{{...}}` không bị hỏng.
- `test_split_no_leakage`: Kiểm tra thuật toán phân chia; đảm bảo mọi nhóm câu trùng chỉ xuất hiện trong đúng 1 fold hoặc tập test, không có giao thoa.
- `test_feature_extractor`: Kiểm tra `IntentFeaturePipeline` fit/transform đúng kích thước, giữ đúng placeholder token và serialize/deserialize bằng joblib nguyên vẹn.

### 4.2. Tiêu chuẩn Nghiệm thu
1. File cấu hình `pipeline/requirements.txt` được tạo và cài đặt thành công trên môi trường `.venv`.
2. Chạy thử nghiệm end-to-end `python -m pipeline.preparation.run_preparation` thành công trên file dữ liệu Bitext thật `data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv`.
3. Toàn bộ các artifact (JSON, CSV, Figures, Joblib) được tạo đầy đủ tại đúng các đường dẫn đã quy định với ID định dạng `<ngày>-<tháng>-<năm>-<stt>`.
4. Toàn bộ unit tests trong `tests/unit/test_preparation.py` chạy qua 100% (Green).
