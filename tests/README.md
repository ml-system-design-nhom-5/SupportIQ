# Hướng dẫn Kiểm thử (Testing Guide) — SupportIQ

## 1. Profiles Kiểm thử

Hệ thống kiểm thử SupportIQ được cấu hình phân tách theo các profile tài nguyên trong `pytest.ini`:

| Marker / Profile | Mục đích | Điều kiện tài nguyên | Lệnh chạy |
|---|---|---|---|
| **Default (CPU/Offline)** | Toàn bộ unit tests & integration tests nội bộ | CPU thuần, zero network, zero external keys | `pytest --basetemp=tmp/pytest/default` |
| **Pure Unit Tests** | Chỉ kiểm tra logic trong `tests/unit/` | Không chạy subprocess / managed server | `pytest tests/unit --basetemp=tmp/pytest/unit` |
| **Integration** | Kiểm tra đa tiến trình, SQLite, loopback HTTP | Loopback localhost 127.0.0.1, SQLite disk | `pytest -m "integration and not real_model and not cuda and not live"` |
| **CUDA / GPU** | Kiểm tra tăng tốc phần cứng GPU NVIDIA | Yêu cầu GPU NVIDIA có CUDA khả dụng | `pytest -m cuda` |
| **Live Network** | Kiểm tra dịch vụ Google AI Studio thật | Cần biến môi trường `GEMINI_API_KEY` | `pytest --run-live -m live` |

---

## 2. Các Lệnh Chạy Chuẩn

```powershell
# Chạy mặc định (Offline CPU & Integration an toàn, bỏ qua GPU & Live)
.venv\Scripts\python.exe -m pytest --basetemp=tmp/pytest/default -q

# Chỉ chạy unit tests phản hồi nhanh
.venv\Scripts\python.exe -m pytest tests/unit --basetemp=tmp/pytest/unit -q

# Chạy integration test loopback
.venv\Scripts\python.exe -m pytest -m "integration and not real_model and not cuda and not live" --basetemp=tmp/pytest/integration -q
```

---

## 3. Dọn Dẹp Cache Kiểm Thử

Script `scripts/clean_test_cache.ps1` hỗ trợ liệt kê và dọn dẹp an toàn các thư mục cache tạm (`.pytest-*`, `tmp/pytest`, `__pycache__` ngoài môi trường ảo):

```powershell
# Xem trước danh sách cache hợp lệ (Dry-run, không xóa)
powershell -ExecutionPolicy Bypass -File scripts/clean_test_cache.ps1

# Thực thi xóa các thư mục cache
powershell -ExecutionPolicy Bypass -File scripts/clean_test_cache.ps1 -Apply
```
