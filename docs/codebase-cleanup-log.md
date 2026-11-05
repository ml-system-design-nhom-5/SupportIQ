# Codebase & Test Cleanup Execution Log

- **Baseline Commit:** `348b827` (`main`)
- **Python Environment:** Python 3.12.14 (`.venv\Scripts\python.exe`)
- **Pytest Baseline:** 382 tests collected across `tests/unit` (357) and `tests/integration` (25)
- **Baseline warnings:** FastAPI `on_event` deprecations; this is historical inventory, not the current result.

---

## 1. Safety & Provenance Invariants (Must Preserve)

| Invariant | Description | Enforcement Point |
|---|---|---|
| **Gate 1 Human Override** | Explicit human request always escalates, even on ML errors or low confidence | `apps/core_backend/intent/routing.py` (Gate 1) |
| **Fail-Closed ML Error** | Invalid or unavailable ML models trigger `manual_fallback`, never uncalibrated mock predictions | `apps/core_backend/intent/routing.py` (Gate 1b) |
| **Scope Protection (34 intents)** | 34 intents outside customer care taxonomy escalate immediately with `must_escalate=True` | `apps/core_backend/intent/routing.py` (Gate 2c) |
| **ACL & Role Verification** | Documents missing matching `allowed_roles` or expired/revoked `valid_to` are excluded | `apps/core_backend/retrieval/adapter.py`, `importer.py` |
| **Pure Semantic Retrieval** | Zero BM25/keyword addition; strictly pure BGE embeddings (`bge-small-en-v1.5`) | `apps/core_backend/retrieval/` |
| **Unified S1..Sn Grounding** | Policy excerpts and authorized business order facts share single `S1..Sn` citation namespace | `apps/core_backend/llm/gemini.py` |
| **Native Process Deadline** | SQLite locks and hanging workers terminated via OS process kill, zero late writes on disk | `pipeline/evaluation/system_server.py` |
| **Demo Session Isolation** | Cross-session replay or feedback rejected with 403; draft revision mismatch rejected with 409 | `apps/demo/service.py` |
| **Immutable Evaluation Lineage** | Evaluation manifests checksum input files and outputs; simulated runs cannot certify live acceptance | `pipeline/evaluation/system_metrics.py`, `assess_system.py` |

---

## 2. Test Inventory & Domain Mapping

- **Total Test Files:** 44 files
- **Total Test Cases Collected:** 382 tests
- **Target Organization:**
  - `tests/unit/intent/` & `tests/unit/` for pure classification & routing
  - `tests/unit/retrieval/` for eligibility, relevance, publication
  - `tests/unit/llm/` for grounding, citations, prompt construction
  - `tests/unit/evaluation/` for contracts, metrics, reporting, provenance
  - `tests/integration/` for multi-process server, loopback HTTP, SQLite persistence

---

## 3. Trạng thái sau xử lý review

Chưa hoàn thành toàn bộ kế hoạch gốc. Lượt sửa review giữ cấu trúc hiện có và sửa các lỗi tài nguyên/ownership; không coi việc test pass là bằng chứng đã thực hiện mọi refactor.

| Task | Trạng thái thực tế |
| --- | --- |
| 1 — Baseline/inventory | Một phần: đã ghi baseline và invariants; chưa có bảng scenario/assertion đầy đủ. |
| 2 — Test profiles | Đã sửa strict markers, marker integration theo thư mục, guard socket/weights/credential và temp UUID. Integration được phép loopback; stdlib socketpair cho asyncio Windows được giữ. |
| 3 — Factories | Một phần: có factories nhưng chưa chuyển các fixture evaluation/comparison lớn sang dùng chung. `offline_retrieval` dùng encoder tổng hợp tường minh cho contract tests. |
| 4 — Domain organization | Chưa di chuyển/gom test theo domain; các test review cũ và assertions được giữ nguyên. Không có test bị xóa hoặc thay thế trong lượt sửa này. |
| 5 — Execution boundaries | Một phần: đã tách mocks và oversight; dataclass/factory/budget wrapper vẫn ở `system_execution.py`. |
| 6 — Metrics extraction | Chưa thực hiện; hai hàm latency vẫn giữ hợp đồng riêng. Không tạo module chỉ để đánh dấu hoàn thành. |
| 7 — Lifespan | Đã chuyển lifespan; app chỉ đóng client tự tạo, không đóng runner/client mượn. Cleanup chạy cả khi exception. |
| 8 — Cache cleanup | Đã sửa: dry-run mặc định, allowlist, từ chối tracked/link/reparse, lock phối hợp pytest. Chỉ kiểm thử Apply trong repo tạm. |
| 9 — Verification | Đã kiểm chứng bản sửa review bằng default/integration/CUDA và checksum; clean-checkout toàn bộ kế hoạch vẫn chưa được chứng nhận. |

## 4. Phạm vi và giới hạn kiểm chứng

- Giữ nguyên đường dẫn/import của các test hiện có; thêm regression cho profile, lifespan và cache cleaner. Không giảm assertions hoặc dùng skip để che lỗi.
- Default pytest chặn socket ngoài loopback được đánh dấu integration, chặn tải tokenizer/weights kể cả từ cache nếu không có marker `real_model`, không nạp `.env`, bỏ credential kế thừa cho từng test. Test có thể tự inject fake credentials/MockTransport.
- Mỗi pytest session giữ `.pytest-cleanup.lock`; cleaner cần quyền mở độc quyền. Dừng những phiên pytest cũ khởi động trước bản sửa này trước lần cleanup đầu tiên.
- Không chạy paid/live benchmark hoặc dọn cache thật trong lượt sửa. Không sửa artifact lịch sử hay `docs/CHỦ ĐỀ 1.md`.

## 5. Kết quả chạy lại sau sửa review

- `.venv\Scripts\python.exe -m pytest -q`: **402 passed, 1 deselected**, 80,52 giây. Dùng temp UUID tự tạo; GPU bị loại đúng profile mặc định.
- Integration selector trong README: **31 passed**. Kết quả trước các test DNS mới (đều là unit) vẫn bao phủ toàn bộ integration hiện có.
- `tests/unit/test_torch_cuda.py -m cuda`: **1 passed** trên phần cứng hiện tại.
- TDD: ca cache trong repo tạm, ownership, socket/UDP/DNS, weights và live preflight đã được thấy fail trước bản sửa tương ứng rồi pass. Không gọi DNS ngoài máy khi kiểm thử native resolver.
- Review bổ sung không tìm thấy regression cleanup/ownership; khoảng trống native DNS được phát hiện và đã sửa trước lượt full suite cuối.
- Hai manifest lịch sử `05-11-2026-system-live-experimental-00` và `05-11-2026-system-http-assessment-00`: **19/19 checksum khớp**; không viết lại artifact.
- Không chạy live/API trả phí, không `-Apply` vào repository thật, không commit/push. Các Task 1/3/4/5/6 còn thiếu được giữ nguyên trạng thái ở bảng trên.
