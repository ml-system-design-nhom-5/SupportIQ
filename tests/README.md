# Hướng dẫn Kiểm thử (Testing Guide) — SupportIQ

## 1. Profiles Kiểm thử

Hệ thống kiểm thử SupportIQ được cấu hình phân tách theo các profile tài nguyên trong `pytest.ini`:

| Marker / Profile | Mục đích | Điều kiện tài nguyên | Lệnh chạy |
|---|---|---|---|
| **Default (CPU/Offline)** | Toàn bộ unit tests & integration tests nội bộ | CPU; chỉ loopback cho integration, không credential thật | `pytest --basetemp=tmp/pytest/default` |
| **Tests trong unit/** | Chỉ kiểm tra logic trong `tests/unit/` | Giữ bố cục hiện có; một số regression vẫn dùng process/SQLite | `pytest tests/unit --basetemp=tmp/pytest/unit` |
| **Integration** | Kiểm tra đa tiến trình, SQLite, loopback HTTP | Loopback localhost 127.0.0.1, SQLite disk | `pytest -m "integration and not real_model and not cuda and not live"` |
| **CUDA / GPU** | Kiểm tra tăng tốc phần cứng GPU NVIDIA | Yêu cầu GPU NVIDIA có CUDA khả dụng | `pytest -m cuda` |
| **Live Network** | Kiểm tra dịch vụ Google AI Studio thật | Cần biến môi trường `GEMINI_API_KEY` | `pytest --run-live -m live` |

---

## 2. Các Lệnh Chạy Chuẩn

```powershell
# Chạy mặc định (Offline CPU & Integration an toàn, bỏ qua GPU & Live)
.venv\Scripts\python.exe -m pytest --basetemp=tmp/pytest/default -q

# Chạy các test đang nằm trong unit/ (còn regression dùng process/SQLite)
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


## 4. Isolation và giới hạn

Không truyền `--basetemp` thì pytest tự tạo `tmp/pytest/<UUID>`; các đường dẫn cố định ở ví dụ chỉ dùng cho một run tại một thời điểm. Không dùng chung basetemp giữa các run song song.

`tests/integration/` được gắn marker `integration` khi collection. Default guard chỉ cho các test này (hoặc test có marker integration tường minh) mở loopback; remote socket bị chặn. MockTransport không bị ảnh hưởng. `socketpair` nội bộ của asyncio Windows được giữ để event loop hoạt động.

Tokenizer/weights bị chặn trong default test kể cả có cache. Muốn kiểm thử weights thật cần test gắn `real_model` và chọn `-m real_model`; đây là profile dành riêng, không phải chuyển toàn bộ contract tests sang model thật. Default test không nạp `.env` và không dùng API key kế thừa. Live test cần đồng thời `--run-live -m live` và `GEMINI_API_KEY` cung cấp tường minh; thiếu key sẽ dừng preflight.

Cleaner từ chối chạy khi pytest đang giữ `.pytest-cleanup.lock`, bỏ qua cây có file tracked hoặc junction/symlink và không quét môi trường ảo. Dừng các pytest cũ khởi động trước bản sửa lock trước lần dọn đầu tiên. Không xóa lock file để vượt kiểm tra phiên đang chạy.

Các lệnh profile chỉ chạy test đã gắn marker, không tự tạo smoke test hay benchmark. Nếu không có test phù hợp thì pytest báo không collect; đó không phải kết quả pass của profile.
