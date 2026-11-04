# DistilBERT 10-Fold Cross-Validation Retraining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Huấn luyện lại mô hình pretrained DistilBERT (`distilbert-base-uncased`) trên toàn bộ 37.911 mẫu dữ liệu phát triển (`partition == 'train'`) bằng giao thức 10-fold cross-validation dựa trên phân bổ fold trong `artifacts/preparation/03-11-2026-02/split_assignments.csv`, sinh out-of-fold metrics, refit checkpoint hoàn chỉnh chuẩn safetensors và cập nhật benchmark so sánh 5 mô hình với provenance độc lập đã xác minh.

**Architecture:** 
- Nâng cấp môi trường PyTorch CUDA nhằm khai thác GPU NVIDIA GeForce RTX 5060 (8GB VRAM) để tăng tốc huấn luyện 10 fold DistilBERT (~34.120 mẫu train / 3.791 mẫu val mỗi fold) với mixed precision FP16/AMP.
- Xây dựng quy trình 10-fold cross-validation tuần tự theo đúng `fold_0`..`fold_9` định nghĩa sẵn trong Preparation run `03-11-2026-02`, cách ly tuyệt đối 6.690 mẫu hold-out test (`partition == 'test'`).
- Thu thập đầy đủ out-of-fold predictions, tính Macro-F1 (mean ± std), Accuracy (mean ± std) trên 37.911 mẫu phát triển tương đương giao thức của 3 baseline scikit-learn.
- Refit mô hình cuối trên toàn bộ 37.911 mẫu, xuất checkpoint chuẩn safetensors vào `artifacts/models/trained/distilbert-supportiq/` kèm `training_report.json` và `train_sample_ids.json` (bằng chứng loại trừ test).
- Tích hợp bằng chứng provenance vào `pipeline/configs/comparison.json` và chạy lại `pipeline/evaluation/run_comparison.py` để chứng nhận `supportiq_distilbert` là mô hình hold-out độc lập có đủ đối soát 10-fold CV.

**Tech Stack:** Python 3.12, PyTorch with CUDA (cu124/cu126), HuggingFace Transformers, Safetensors, scikit-learn, pandas, numpy.

**Spec:** [Kế hoạch so sánh 5 mô hình](2026-11-03-compare-transformers-baselines.md), [Đặc tả Training](../specs/2026-11-03-pipeline-training-design.md), [Đặc tả Evaluation](../specs/2026-11-03-pipeline-evaluation-design.md).

## Global Constraints

* Dữ liệu huấn luyện: Đúng 37.911 mẫu từ `artifacts/preparation/03-11-2026-02/cleaned.csv` có `partition == 'train'` trong `split_assignments.csv`. Tuyệt đối không nạp hoặc rò rỉ bất kỳ mẫu nào trong số 6.690 mẫu `partition == 'test'`.
* Taxonomy nhãn: Cố định 46 intent chuẩn (`STANDARD_INTENTS`), ánh xạ `label2id` và `id2label` sắp xếp theo thứ tự bảng chữ cái để đồng bộ toàn hệ thống.
* Định dạng trọng số: Bắt buộc xuất `model.safetensors`, tuyệt đối không dùng pickle `.bin`. Nạp mô hình luôn yêu cầu `use_safetensors=True`.
* Giao thức CV: Đúng 10 fold (`fold` 0 đến 9), không xáo trộn lại chỉ số fold đã cố định bởi Preparation run `03-11-2026-02`.
* Tính toàn vẹn: Mọi artifact đầu ra (`training_report.json`, `train_sample_ids.json`, `oof_predictions.csv`, `fold_metrics.csv`) phải có cấu trúc tường minh và băm SHA-256 để kiểm chứng lineage.

## Review Focus

1. **Rò rỉ tập hold-out test vào huấn luyện:** Xác minh tập train chỉ chứa sample IDs có `partition == 'train'` và `test_sample_ids` giao nhau bằng tập rỗng (`overlap == 0`).
2. **CUDA out-of-memory (OOM) hoặc xung đột driver:** Cấu hình batch size hợp lý (32 hoặc 16) kết hợp mixed precision AMP (`torch.cuda.amp.autocast`) và giải phóng bộ nhớ đệm `torch.cuda.empty_cache()` sau mỗi fold.
3. **Mất nhãn hoặc sai taxonomy trong config HuggingFace:** Kiểm tra `config.json` chứa đầy đủ 46 nhãn trong `id2label`, không chứa `LABEL_0` ngẫu nhiên.
4. **Bảo toàn định dạng Safetensors:** Đảm bảo thư mục lưu trữ chỉ chứa `model.safetensors`, không sinh file `pytorch_model.bin`.
5. **Khớp nối Provenance Verification:** File `train_sample_ids.json` phải được `pipeline/evaluation/comparison_contracts.py` chấp nhận, chuyển cờ provenance từ `unverified` sang `verified`.

---

## Task 1: Cập nhật PyTorch CUDA cho môi trường & Viết GPU Smoke Test

**Files:**
- Modify: `.venv` dependencies (cài đặt `torch` với CUDA qua `uv`)
- Create: `tests/unit/test_torch_cuda.py`

**Interfaces:**
- Consumes: Môi trường Windows x86_64, NVIDIA Driver 610.88, RTX 5060 (8GB VRAM)
- Produces: `torch.cuda.is_available() == True`, `torch.cuda.get_device_name(0)`

- [ ] **Step 1: Write smoke test for PyTorch CUDA availability and forward pass**

```python
# tests/unit/test_torch_cuda.py
import torch
import pytest

def test_torch_cuda_functional():
    assert torch.cuda.is_available(), "CUDA must be available in .venv"
    device = torch.device("cuda:0")
    x = torch.randn(10, 64, device=device)
    linear = torch.nn.Linear(64, 46).to(device)
    y = linear(x)
    assert y.shape == (10, 46)
    assert y.is_cuda
```

- [ ] **Step 2: Run test to verify failure (currently CPU torch)**

Run: `pytest tests/unit/test_torch_cuda.py -v`
Expected: FAIL with "CUDA must be available in .venv"

- [ ] **Step 3: Cài đặt PyTorch với CUDA trong `.venv` bằng `uv`**

Cài đặt wheel `torch` tương thích CUDA (ví dụ cu124/cu126) bằng lệnh:
`uv pip install --reinstall torch --index-url https://download.pytorch.org/whl/cu124` (hoặc cu126)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_torch_cuda.py -v`
Expected: PASS

- [ ] **Step 5: Verify existing 149 pipeline tests still pass**

Run: `pytest tests/unit/test_preparation.py tests/unit/test_training.py tests/unit/test_evaluation_ml.py tests/unit/test_model_comparison.py -v`
Expected: 149 passed

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_torch_cuda.py
git commit -m "chore(env): enable CUDA PyTorch for RTX 5060 acceleration"
```

---

## Task 2: Xây dựng Module Huấn luyện 10-Fold CV cho DistilBERT

**Files:**
- Create: `pipeline/training/train_distilbert_cv.py`
- Create: `tests/unit/test_distilbert_cv.py`

**Interfaces:**
- Consumes:
  - `artifacts/models/pretrained/distilbert-base-uncased/`
  - `artifacts/preparation/03-11-2026-02/cleaned.csv`
  - `artifacts/preparation/03-11-2026-02/split_assignments.csv`
- Produces:
  - `run_distilbert_10fold_cv(...) -> dict[str, Any]`
  - Output artifacts: `fold_metrics.csv`, `oof_predictions.csv`, `training_report.json`, `train_sample_ids.json`

- [ ] **Step 1: Write unit test for DistilBERT 10-fold CV data partitioning & metric calculation**

Kiểm tra:
1. `test_cv_dataset_strict_train_filter`: từ chối dữ liệu chứa nhãn lạ hoặc mẫu test partition.
2. `test_cv_oof_aggregation`: tính đúng mean/std của Macro-F1 từ các fold.
3. `test_sample_ids_containment`: file `train_sample_ids.json` chứa đúng 37.911 ID và có overlap = 0 với 6.690 test IDs.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_distilbert_cv.py -v`
Expected: FAIL (module `train_distilbert_cv` not found)

- [ ] **Step 3: Implement `pipeline/training/train_distilbert_cv.py`**

Triển khai logic:
1. `load_and_verify_cv_data(cleaned_csv, splits_csv)`:
   - Merge `cleaned.csv` và `split_assignments.csv` theo `sample_id`.
   - Lọc strictly `partition == 'train'`, xác nhận đúng 37.911 dòng và `fold` trong $0..9$.
   - Trích xuất 6.690 test sample IDs để kiểm tra overlap.
2. `train_one_fold(fold, train_df, val_df, model_path, config)`:
   - Huấn luyện DistilBERT trên GPU với `torch.cuda.amp.autocast`.
   - Đánh giá val split, trả về predictions và metrics (`macro_f1`, `accuracy`, `weighted_f1`).
3. `run_distilbert_10fold_cv(...)`:
   - Lặp qua 10 fold.
   - Ghi nhận `fold_metrics.csv` và `oof_predictions.csv`.
   - Tính mean ± std cho `macro_f1` và `accuracy`.
   - Lưu `train_sample_ids.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_distilbert_cv.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/train_distilbert_cv.py tests/unit/test_distilbert_cv.py
git commit -m "feat(training): implement 10-fold CV module for DistilBERT"
```

---

## Task 3: Refit Mô hình Cuối trên 37.911 mẫu & Xuất Checkpoint Safetensors Chuẩn

**Files:**
- Modify: `pipeline/training/train_distilbert_cv.py`
- Modify: `tests/unit/test_distilbert_cv.py`

**Interfaces:**
- Consumes: Toàn bộ 37.911 mẫu tập phát triển, pretrained checkpoint `distilbert-base-uncased`
- Produces: Thư mục mô hình `artifacts/models/trained/distilbert-supportiq/` chứa:
  - `model.safetensors`
  - `config.json`
  - `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `vocab.txt`
  - `training_report.json` (ghi nhận `training_samples: 37911`, `cv_protocol: "10-fold cross-validation"`, `cv_macro_f1_mean`, `cv_macro_f1_std`)
  - `train_sample_ids.json` (danh sách 37.911 ID)

- [ ] **Step 1: Write test for final refit and safetensors format verification**

Kiểm tra:
1. `test_refit_produces_safetensors_without_bin`: Thư mục đầu ra có `model.safetensors` và không có `.bin`.
2. `test_training_report_schema`: Báo cáo có `training_samples == 37911`, `cv_protocol == "10-fold cross-validation"`, `cv_macro_f1_mean > 0.95`.
3. `test_model_can_be_loaded_by_transformer_adapter`: Nạp thử bằng `TransformerClassifierAdapter` và thực hiện `predict()` thành công.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_distilbert_cv.py -k "test_refit" -v`
Expected: FAIL

- [ ] **Step 3: Implement final refit & checkpoint emission in `train_distilbert_cv.py`**

- Sau khi kết thúc 10 fold CV, tiến hành refit trên toàn bộ 37.911 mẫu (2 epochs, lr=3e-5, batch_size=32).
- Lưu mô hình và tokenizer với `save_pretrained(output_dir, safe_serialization=True)`.
- Ghi đè hoặc cập nhật `training_report.json` và `train_sample_ids.json` vào thư mục mô hình.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_distilbert_cv.py -k "test_refit" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/training/train_distilbert_cv.py tests/unit/test_distilbert_cv.py
git commit -m "feat(training): add full refit and atomic safetensors export"
```

---

## Task 4: Chạy Huấn luyện 10-Fold CV & Sinh Artifacts Chính thức

**Files:**
- Execute: `pipeline/training/train_distilbert_cv.py`
- Target outputs:
  - `artifacts/models/trained/distilbert-supportiq/model.safetensors`
  - `artifacts/models/trained/distilbert-supportiq/config.json`
  - `artifacts/models/trained/distilbert-supportiq/training_report.json`
  - `artifacts/models/trained/distilbert-supportiq/train_sample_ids.json`
  - `artifacts/training/distilbert_cv/fold_metrics.csv`
  - `artifacts/training/distilbert_cv/oof_predictions.csv`

- [ ] **Step 1: Chạy script huấn luyện 10-Fold CV trên GPU RTX 5060**

Lệnh thực thi:
```bash
python -m pipeline.training.train_distilbert_cv \
  --pretrained-model-dir artifacts/models/pretrained/distilbert-base-uncased \
  --cleaned-csv artifacts/preparation/03-11-2026-02/cleaned.csv \
  --splits-csv artifacts/preparation/03-11-2026-02/split_assignments.csv \
  --output-dir artifacts/models/trained/distilbert-supportiq \
  --cv-metrics-dir artifacts/training/distilbert_cv \
  --epochs 2 \
  --batch-size 32 \
  --lr 3e-5
```

- [ ] **Step 2: Kiểm tra tính đầy đủ và tính toàn vẹn của artifacts sinh ra**

Kiểm tra:
- 10 fold hoàn thành không lỗi.
- `training_report.json` ghi nhận đủ `train_samples: 37911`, `cv_protocol: "10-fold cross-validation"`, `cv_macro_f1_mean`, `cv_macro_f1_std`.
- `train_sample_ids.json` tồn tại, chứa đúng 37.911 ID.
- Checksum SHA-256 của `model.safetensors` được tạo mới.

- [ ] **Step 3: Commit kết quả hoặc báo cáo metadata**

```bash
git add artifacts/models/trained/distilbert-supportiq/training_report.json artifacts/models/trained/distilbert-supportiq/train_sample_ids.json
git commit -m "feat(models): retrain distilbert-supportiq with 10-fold CV on 37911 samples"
```

---

## Task 5: Cập nhật Cấu hình So sánh, Chạy lại Benchmark & Xác minh Toàn diện

**Files:**
- Modify: `pipeline/configs/comparison.json`
- Output: `artifacts/evaluation/<new_run_id>/`
- Test: Toàn bộ unit tests

**Interfaces:**
- Consumes:
  - `artifacts/models/trained/distilbert-supportiq/` (đã huấn luyện 10-fold CV)
  - `artifacts/models/trained/distilbert-supportiq/train_sample_ids.json`
  - `artifacts/training/03-11-2026-00/manifest.json` (baselines)
- Produces:
  - Báo cáo so sánh 5 mô hình cập nhật: `supportiq_distilbert` được chứng nhận provenance `verified` độc lập, có Macro-F1 CV trên 37.911 mẫu sánh vai cùng các baseline.

- [ ] **Step 1: Cập nhật `pipeline/configs/comparison.json`**

Thêm thông tin `membership_evidence` gắn với file `train_sample_ids.json` và SHA-256 hash của nó:
```json
"supportiq_distilbert": {
  "type": "transformer",
  "model_dir": "artifacts/models/trained/distilbert-supportiq",
  "provenance": {
    "origin": "local_finetuned",
    "base_model": "distilbert/distilbert-base-uncased",
    "membership_evidence": {
      "evidence_path": "artifacts/models/trained/distilbert-supportiq/train_sample_ids.json",
      "evidence_sha256": "<SHA256_HASH>"
    }
  }
}
```

- [ ] **Step 2: Thực thi runner so sánh 5 mô hình**

Run: `python -m pipeline.evaluation.run_comparison --config pipeline/configs/comparison.json`
Expected: Completed successfully, tạo run `artifacts/evaluation/<id>/` với bảng so sánh CPU chuẩn và GPU profile.

- [ ] **Step 3: Kiểm tra báo cáo `report.md` và `summary.json` trong run mới**

Xác nhận:
- `supportiq_distilbert` có provenance status `verified`.
- CV Macro-F1 hiển thị số liệu từ 10-fold CV trên 37.911 mẫu.
- Điểm test hold-out độc lập (6.690 mẫu) được xếp hạng chính thức bên cạnh Linear SVM, Logistic Regression và Multinomial NB.

- [ ] **Step 4: Chạy toàn bộ regression test suite**

Run: `pytest tests/unit -v`
Expected: 100% tests pass.

- [ ] **Step 5: Commit hoàn tất**

```bash
git add pipeline/configs/comparison.json
git commit -m "feat(evaluation): update comparison benchmark with verified 10-fold CV DistilBERT"
```
