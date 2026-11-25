# Hướng dẫn Kiểm thử (Testing Guide) — Pipeline & Unit Tests

Thư mục `tests/` dành riêng cho việc kiểm thử đơn vị và kiểm thử chất lượng của phân hệ học máy độc lập (`pipeline/`):
- **Tiền xử lý & Chuẩn hóa (`pipeline.preparation.preprocessing`)**: `test_placeholders.py`, `test_clause_split.py`.
- **Chuẩn bị dữ liệu (`pipeline/preparation/`)**: `test_preparation.py`, `test_intent_extra.py`.
- **Huấn luyện mô hình (`pipeline/training/`)**: `test_augment.py`, `test_training.py`, `test_distilbert_cv.py`.
- **Đánh giá mô hình offline (`pipeline/evaluation/`)**: `test_retrieval_evaluation.py`, `test_routing_evaluation.py`, `test_evaluation_ml.py`, `test_model_comparison.py`.

> **Lưu ý phân định ranh giới kiến trúc:**
> - Kiểm thử tích hợp backend, quyền hạn, cơ sở dữ liệu PostgreSQL, và nghiệp vụ ticket thuộc về: [`backend/tests/`](../backend/tests/).
> - Kiểm thử môi trường triển khai và chạy thử HTTP local thuộc về: [`deploy/local/tests/`](../deploy/local/tests/).
> - Toàn bộ thư mục `apps/` và các harness đánh giá hệ thống cũ phụ thuộc vào nó đã được dỡ bỏ hoàn toàn.

## 1. Profiles Kiểm thử

Hệ thống kiểm thử được cấu hình phân tách theo các profile tài nguyên trong `pytest.ini`:

| Marker / Profile | Mục đích | Điều kiện tài nguyên | Lệnh chạy |
|---|---|---|---|
| **Default (CPU/Offline)** | Toàn bộ unit tests pipeline offline | CPU; không credential thật | `python -m pytest tests/` |
| **CUDA / GPU** | Kiểm tra tăng tốc phần cứng GPU NVIDIA | Yêu cầu GPU NVIDIA có CUDA khả dụng | `pytest -m cuda` |
| **Real Model** | Kiểm thử nạp trọng số mô hình thực tế từ disk | Cần có artifact mô hình đã tải | `pytest -m real_model` |
| **Live Network** | Kiểm tra dịch vụ Google AI Studio thật | Cần biến môi trường `GEMINI_API_KEY` | `pytest --run-live -m live` |

---

## 2. Các Lệnh Chạy Chuẩn

```bash
# Chạy mặc định toàn bộ test pipeline offline
python -m pytest tests/ -q

# Chạy riêng kiểm thử tiền xử lý
python -m pytest tests/unit/test_placeholders.py tests/unit/test_clause_split.py -q
```
