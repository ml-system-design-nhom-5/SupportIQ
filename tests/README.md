# Hướng dẫn Kiểm thử (Testing Guide) — SupportIQ

## 1. Profiles Kiểm thử

Hệ thống kiểm thử SupportIQ được cấu hình phân tách theo các profile tài nguyên trong `pytest.ini` (`addopts = --strict-markers -m "not real_model and not cuda and not live"`). Xem thêm tài liệu CI và xác minh tại [tài liệu autoeval](../docs/autoeval.md) và [hướng dẫn xác minh ứng dụng](../docs/guides/application-verification.md).

| Marker / Profile | Mục đích | Điều kiện tài nguyên | Lệnh chạy |
|---|---|---|---|
| **Default (`not real_model and not cuda and not live`)** | Toàn bộ tập offline mặc định: hiện collect `1027` tests (`845` unit, `122` application, `31` integration, `29` e2e) và deselect `3` tests | Chạy trên CPU với socket non-loopback bị chặn, tắt dotenv/API keys (độc lập với việc `.venv` cài PyTorch CPU hay CUDA); **không phải thuần unit-only** vì `tests/application/` kết nối PostgreSQL khi có cấu hình `SUPPORTIQ_APPLICATION_SECRETS` / `.local/application.json` | `pytest --basetemp=tmp/pytest/default` |
| **Tests trong unit/** | Chỉ chạy kiểm thử trong `tests/unit/` (`845` collected mặc định; còn một số regression dùng process/SQLite) | CPU, không tải weight HF thật | `pytest tests/unit --basetemp=tmp/pytest/unit` |
| **Integration** | Kiểm tra đa tiến trình, SQLite, loopback HTTP | Loopback `127.0.0.1`, SQLite disk | `pytest -m "integration and not real_model and not cuda and not live"` |
| **Real Model (`real_model`)** | Kiểm tra inference với weight phát hành thật (`tests/unit/test_autoeval.py`, `tests/unit/test_task_c_evaluation_gates.py`) | Đã tải model release hợp lệ; không chạy trong default offline | `pytest -m real_model` |
| **CUDA / GPU (`cuda`)** | Kiểm tra tăng tốc phần cứng GPU NVIDIA | Yêu cầu GPU NVIDIA có CUDA khả dụng | `pytest -m cuda` |
| **Live Network (`live`)** | Kiểm tra dịch vụ Google AI Studio thật | Cần cờ `--run-live` và biến môi trường `GEMINI_API_KEY` | `pytest --run-live -m live` |

> **Phân biệt skip do thiếu config với lỗi kết nối/setup PostgreSQL trong Default profile:**
> - **Skip có điều kiện khi thiếu config:** `tests/application/test_application.py` và `tests/application/test_backend_safety_closure.py` gọi `pytest.skip(...)` chỉ khi thiếu file secrets (`SUPPORTIQ_APPLICATION_SECRETS` / `.local/application.json`), và `test_backend_safety_closure.py` skip riêng bài kiểm tra runtime role nếu JSON thiếu `database_url_app`. Ngoài ra `tests/unit/test_review_eight_fixes.py` skip case acceptance khi không có file local tùy chọn `data/benchmarks/system/v3/acceptance/cases.jsonl`.
> - **Fail khi PostgreSQL không kết nối được / setup DB lỗi:** Khi file secrets tồn tại (hoặc trong `tests/application/test_intent_correction_diagnostic.py` dùng `resolve_database_url()`), fixture mở kết nối PostgreSQL thật và chạy `CREATE SCHEMA`; nếu dịch vụ PostgreSQL đang tắt, không truy cập được hoặc sai quyền sẽ **fail ở bước DB setup**, **không** tự động skip.
> - Trên Windows có Application Control chặn `psycopg_binary`, đặt `$env:PSYCOPG_IMPL="python"` và thêm `F:\PostgreSQL\bin` vào `PATH` để dùng driver pure-Python + `libpq`.

---

## 2. Các Lệnh Chạy Chuẩn

> Trên Windows của workspace này, dùng `.venv\Scripts\python.exe` (Python 3.12 của project; hiện cài `torch 2.11.0+cu128` bản CUDA) thay vì `python` toàn cục khi chạy các test import `torch`. Profile mặc định (`not real_model and not cuda and not live`) chỉ chạy nhánh CPU/offline độc lập với bản build `torch` của môi trường.

```powershell
# 1. Mặc định (CPU/offline + integration loopback + application DB nếu có secrets; bỏ qua 3 test real_model/cuda/live)
.venv\Scripts\python.exe -m pytest --basetemp=tmp/pytest/default -q

# 2. Chạy application tests với PostgreSQL trên Windows khi psycopg_binary bị chặn
$env:PSYCOPG_IMPL = "python"
$env:PATH = "F:\PostgreSQL\bin;$env:PATH"
.venv\Scripts\python.exe -m pytest tests/application --basetemp=tmp/pytest/application -q

# 3. Chỉ tests trong unit/ (không phụ thuộc PostgreSQL)
.venv\Scripts\python.exe -m pytest tests/unit --basetemp=tmp/pytest/unit -q

# 4. Integration test loopback
.venv\Scripts\python.exe -m pytest -m "integration and not real_model and not cuda and not live" --basetemp=tmp/pytest/integration -q

# 5. Frontend unit tests (Vitest), build và liệt kê E2E Playwright (apps/frontend)
pnpm.cmd --dir apps/frontend test
pnpm.cmd --dir apps/frontend build
pnpm.cmd --dir apps/frontend exec playwright test --list
```

### Tương đương CI Dự kiến (Offline; chưa xác nhận hosted CI)

> Kiến trúc CI GitHub Actions (`ci.yml` và bản cập nhật `autoeval.yml`) hiện là **kế hoạch CI dự kiến** chờ tích hợp Worker B và chạy trên hosted GitHub Actions; kiểm thử cục bộ trên Windows không đồng nghĩa hosted CI đã xanh, và **không có paid LLM calls nào được phép chạy trong CI**.

- **Python + PostgreSQL (offline, dự kiến trên Linux CI):** chạy tập default với PostgreSQL disposable và `GEMINI_API_KEY` bị tắt bởi `tests/conftest.py`.
- **Frontend:** `pnpm.cmd --dir apps/frontend test` và `pnpm.cmd --dir apps/frontend build`.
- **Autoeval LLM offline:** `.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --suite llm --llm-mode offline` (exit code thật; xem [tài liệu autoeval](../docs/autoeval.md)). Các bài đánh giá ML đòi weight thật (`-m real_model`, `--suite ml`) **không** được đánh giá trong CI offline thông thường khi chưa cấp model release.

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

---

## 5. Bản đồ Hành vi & Sở hữu Kiểm thử (Behavior Map)

Phạm vi kiểm tra tách bạch giữa kiểm chứng giả lập offline (unit/contract/structural), kiểm chứng ứng dụng có PostgreSQL, kiểm chứng với model phát hành (`real_model`), và kiểm chứng live có trả phí (`live`):

| Miền hành vi | Nhóm module sở hữu chính | Profile / Điều kiện | Bất biến & ranh giới |
|---|---|---|---|
| **System contracts, metrics, assessment, execution** | `tests/unit/test_system_*.py`, `tests/unit/test_gemini_llm.py`, `tests/unit/test_retry_draft.py`, `tests/unit/test_completion_http_clients.py` | Default offline (fake transports/subprocesses) | Cô lập sự cố tiến trình (`IsolatedCaller`), timeout/deadline, retry/resilience của LLM client, deduplication và contract dữ liệu |
| **Historical review & safety regression probes** | [`unit/test_review_eight_fixes.py`](unit/test_review_eight_fixes.py) (9 tests), [`unit/test_system_review_probes.py`](unit/test_system_review_probes.py) (12 tests), [`unit/test_system_review_probes_v2.py`](unit/test_system_review_probes_v2.py) (8 tests) | Default offline (1 case acceptance skip nếu thiếu `data/benchmarks/system/v3/acceptance/cases.jsonl`) | Giữ nguyên 29 tests sau rà soát (xem mục 6 bên dưới): bảo vệ riêng pooling của client chưa tiêm transport, hủy tác vụ `IsolatedCaller`, `as_of=None`, unsigned candidate và `kb_coverage_gap` |
| **Autoeval & grounding gates** | `tests/unit/test_autoeval.py`, `tests/unit/test_task_c_evaluation_gates.py`, `tests/unit/test_input_snapshot_persistence.py` | Default offline (structural/contract); `real_model` cho kiểm tra weight phát hành | Kiểm tra cấu trúc citation/grounding/exit code **không** chứng minh semantic grounding; review AI được ủy quyền (`--judge` / AI coordinator) phải gắn nhãn rõ là AI review (`human_participants = 0`), không gắn nhãn là human study |
| **Profile isolation & loopback integration** | `tests/unit/test_test_profiles.py`, `tests/integration/*.py` | Default offline / `-m integration` | `tests/conftest.py` chặn non-loopback sockets, HF download và API keys khi không chạy `live`/`real_model` |
| **Application API, DB safety, retry & workflow privacy** | `tests/application/test_application.py`, `tests/application/test_backend_safety_closure.py`, `tests/application/test_workflow_privacy.py`, `tests/application/test_llm_retry.py`, `tests/application/test_provider_recovery_b.py` | Default (cần PostgreSQL khi chạy suite DB; thiếu file secrets skip, còn lỗi kết nối khi có secrets sẽ fail setup) | Bảo vệ PII redaction, quyền runtime role, retry/provider recovery và cô lập schema tạm; không gọi LLM thật nếu không bật `live` |
| **Python full-pipeline E2E & Frontend UI/Playwright** | `tests/e2e/test_full_pipeline.py` (Python pipeline E2E); `apps/frontend/src/components/reply-rules.test.ts` & `apps/frontend/src/features/*.test.tsx` (Vitest); `apps/frontend/e2e/application.spec.ts` (`apps/frontend/playwright.config.ts`) | Default offline cho `tests/e2e/test_full_pipeline.py` & Vitest; Playwright cần browser/server | `tests/e2e/test_full_pipeline.py` kiểm tra luồng Python/SQLite end-to-end với mock HTTP/LLM; frontend `application.spec.ts` tách riêng cho trình duyệt thật và không nằm trong default pytest |

---

## 6. Ghi nhận Rà soát Gom nhóm Regression Probes

Sau kiểm tra trực tiếp từng assertion trong [`unit/test_review_eight_fixes.py`](unit/test_review_eight_fixes.py) (9 tests), [`unit/test_system_review_probes.py`](unit/test_system_review_probes.py) (12 tests), và [`unit/test_system_review_probes_v2.py`](unit/test_system_review_probes_v2.py) (8 tests) đối chiếu với `tests/unit/test_system_execution.py`, `tests/unit/test_system_assessment.py`, `tests/unit/test_system_metrics.py`, `tests/unit/test_system_contracts.py` và `tests/unit/test_completion_http_clients.py`: **không có cặp trùng lặp an toàn để xóa hoặc gộp**. Mỗi test đều khóa một điều kiện hồi quy riêng (ví dụ: pooling của `IntentClient()` không tiêm transport so với `MockTransport`, `IsolatedCaller` kết thúc dưới `0.25s` với `is_running() is False`, xử lý `as_of=None`, deduplication claim, từ chối candidate chưa ký và `kb_coverage_gap`), nên toàn bộ 29 tests được giữ nguyên nguyên vẹn.
