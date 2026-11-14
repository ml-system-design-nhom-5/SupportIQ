# SupportIQ Topic 1 Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khắc phục model provenance, tái lập chạy thử và tạo bằng chứng nghiệm thu trung thực theo Chủ đề 1.

**Architecture:** Giữ React → FastAPI/PostgreSQL → AI gateway hiện có. Ưu tiên provenance và an toàn, sau đó thống nhất evaluation; không viết lại hệ thống.

**Tech Stack:** Python/FastAPI, PyTorch/Transformers, PostgreSQL/SQLAlchemy, React/TypeScript, pytest, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-12-topic-1-improvements-design.md`.

## Trạng thái thực thi ngày 12-11-2026

Người dùng đã ủy quyền thực thi với 3 worker Antigravity và coordinator review/tích hợp. Các checkbox bên dưới giữ nội dung kế hoạch gốc, không phải bằng chứng hoàn thành. Bằng chứng và thay đổi phạm vi nằm trong [báo cáo tích hợp](../../audits/2026-11-12-topic-1-integration.md).

| Task | Trạng thái |
|---|---|
| 1 — Runtime | Đã tích hợp và chạy startup tự phát hiện PostgreSQL thành công |
| 2 — Model | Đã tích hợp, tests và live trained-model smoke đã chạy |
| 3 — Evidence | Đã tích hợp qua 3 vòng review, có thêm regression fixes tại coordinator |
| 4 — Workflow/privacy | Luồng customer/staff/manager/admin và E2E đã chạy; NER thật là optional skip, helper tests không được gọi là full egress recall |
| 5 — Nghiệm thu | Có live smoke, AI claim grading, agent paired trials, recomputed stored OOF; shared retrieval gold/KB chưa tương thích nên chưa nghiệm thu toàn bộ |
| 6 — Docs | Đã đồng bộ hướng dẫn và công khai giới hạn; các báo cáo cũ vẫn giữ nguyên để truy vết |

## Global Constraints

- Dữ liệu giao dịch và PII phải là giả lập.
- Không tự gửi; authority case chỉ manager gửi; AI lỗi vẫn nhập reply thủ công được.
- Metric thiếu là not_evaluated; mock/fallback không đạt live acceptance.
- Không vô hiệu hóa Application Control để nghiệm thu.
- Giữ English cho model/KB/UI hiện có; tài liệu review bằng tiếng Việt.
- Các ước lượng dưới đây là đề xuất ban đầu, không phải thời gian đo thực tế.

## Review Focus

- Thư mục model tồn tại nhưng thiếu một file không được ready với heuristic giả danh verified.
- Metadata calibration/staff override không được biến thành xác suất model đã kiểm chứng.
- Metric thiếu hoặc report cached không được đánh dấu live/pass.
- Một claim ngắn hoặc citation đúng ID nhưng sai nội dung vẫn phải bị phát hiện khi đánh giá.
- Lỗi AI/DB và concurrent send không được gửi reply sai quyền hoặc làm mất audit.

## Task 1 — P0: Khôi phục môi trường chạy (0,5–1 ngày)

**Files:** kiểm tra `apps/backend/requirements.txt`, `scripts/native_runtime.py`, `scripts/start-app.ps1`; cập nhật `docs/guides/application-windows.md`, `docs/guides/application-verification.md`; thêm `tests/unit/test_runtime_preflight.py` nếu thêm preflight.

**Interfaces:** consume Python venv/PostgreSQL local; produce startup `/health/ready` và dependency diagnostics không chứa credentials.

- [ ] Tái hiện riêng import psycopg; ghi interpreter, driver và lỗi DLL; xác định dependency được máy cho phép với quản trị môi trường nếu cần. Không thay policy bảo vệ Windows.
- [ ] Nếu bổ sung preflight: viết test giả lập ImportError, kỳ vọng thông báo đúng dependency/policy và không in connection string; chạy test thấy fail trước sửa.
- [ ] Sửa hướng dẫn/preflight tối thiểu, không tự chuyển ứng dụng sang SQLite để né integration gate.
- [ ] Chạy preflight test, startup `./scripts/start-app.ps1 -SkipInstall -SkipBuild -DisableLLM`, kiểm backend/AI readiness; ghi rõ ready model thật hay degraded.
- [ ] Chạy `pytest tests/application -q`, `pnpm build`, `pnpm test`, `pnpm test:e2e` trong component tương ứng. E2E chỉ sau khi startup thành công; lưu counts và logs đã che dữ liệu.
- [ ] Review và commit riêng phần môi trường; nếu DLL vẫn bị chặn, báo blocked và tiếp tục các unit tasks độc lập.

## Task 2 — P0: Model provenance/fail closed (1–2 ngày; độc lập Task 1 với mocks)

**Files:** sửa `apps/ml_inference/app.py`, `apps/ai_service/main.py`, `apps/ai_service/engine.py`; thêm `tests/unit/test_model_provenance.py`; cập nhật `tests/application/test_ai_boundary.py`, `contracts/backend.openapi.json` và frontend nơi đọc model metadata nếu schema đổi.

**Interfaces:** giữ `ModelContainer.load(model_dir)`, `is_ready()`, `predict(text, ...)`; bổ sung provenance additive theo IMP-03, không đổi tên field hiện hành vô cớ.

- [ ] Viết tests thư mục không có, thiếu từng file, checksum sai; assert không verified/không ready mặc định; chạy thấy fail ở fallback hiện tại.
- [ ] Viết tests explicit demo mode: identity khác trained, checksum không giả, score_kind không calibrated; override source=staff không coi là prediction.
- [ ] Đổi fallback mặc định tắt, hoặc loại khỏi đường application; nếu giữ demo thì dùng metadata riêng. Chỉ gán hash sau khi thực sự hash/verify artifact.
- [ ] Chạy tests provenance và AI boundary; kiểm compatibility của gateway/UI/contract; thêm fixture trained model mock có checksum hợp lệ và real_model opt-in riêng.
- [ ] Chạy smoke với artifact thật khi môi trường cho phép; benchmark phải từ chối heuristic. Review/commit riêng.

## Task 3 — P0: Evidence/report contracts (1–2 ngày)

**Files:** sửa `scripts/evaluate_regression.py`, `pipeline/evaluation/system_reporting.py`, `pipeline/evaluation/system_contracts.py`; thêm `tests/unit/test_evaluation_evidence.py`; tạo report vào thư mục run mới, không ghi đè evidence cũ.

**Interfaces:** consume summary + manifest; produce metric `{value, status, evidence_ref}` cùng evidence_kind/model_mode. Metric thiếu không được mặc định bằng 0; thay đổi consumers và fixtures cùng task.

- [ ] Viết test thiếu hallucination/ECE không pass upper-bound; mock không live-certified; summary cũ thiếu provenance báo insufficient_evidence; chạy thấy fail.
- [ ] Viết test hai run khác KB/split/model hashes không được coi là regression cùng điều kiện; cached-only report ghi rõ không có execution mới.
- [ ] Thực hiện IMP-10/11: manifest run_id/commit/hashes/config/counts/environment, timestamp và raw evidence reference; giữ số liệu cũ nguyên trạng.
- [ ] Chạy unit tests reporting/evidence; tạo fixture report và kiểm mọi PASS truy ngược raw records được. Review/commit.

## Task 4 — P1: Safety, privacy và workflow (1–2 ngày; DB tests sau Task 1)

**Files:** bổ sung `tests/application/test_ai_boundary.py`, `tests/application/test_application.py`, tests engine trong `tests/unit/test_ai_grounding.py`, `apps/frontend/e2e`; chỉ sửa `apps/ai_service/engine.py`, `apps/backend/tickets/privacy.py`, `service.py`, `jobs.py` nếu test chứng minh lỗi.

**Interfaces:** consume routing/reason codes, suggestion state, allowed_actions và human-send API hiện có; produce evidence FR-02…FR-08.

- [ ] Viết failing tests cho expired/conflicting/no sources, multi-intent/OOD, human_agent, chargeback/policy exception, missing order fields và timeout; expected abstain/escalate/manual theo policy hiện có.
- [ ] Kiểm paragraph ngắn chứa thời hạn/tiền và citation đúng ID nhưng unsupported; structural tests không thay chấm claim của Task 5. Chỉ áp checker mới sau khi chọn quy tắc không chặn greeting vô hại.
- [ ] Capture egress bằng fake transport: PII giả lập, placeholder khách tự gõ, tên/địa chỉ ngoài known fields; assert không leak field bị cấm và log không chứa secrets. Ghi recall limitations nếu chưa đạt.
- [ ] Chốt policy regenerate riêng: giữ retry cho transient; phân loại `test_retry_draft.py` là yêu cầu mới hay lỗi test trước khi đưa vào git.
- [ ] DB/E2E: staff không gửi authority case, manager được gửi, customer không thấy draft, admin không đọc ticket; concurrent send chỉ một message, audit không update/delete được. Test green rồi review/commit.

## Task 5 — P1: Nghiệm thu ML/RAG/LLM và product value (2–4 ngày kỹ thuật, chưa tính lịch người chấm)

**Files:** dùng `pipeline/evaluation/evaluate_intent.py`, `evaluate_retrieval.py`, `run_system_evaluation.py`, `scripts/verify_ai_integration.py`; tạo `artifacts/evaluation/<run-id>/` và cập nhật `docs/system-evaluation-report.md` sau khi có kết quả.

**Interfaces:** consume provenance từ Task 2 và report contracts Task 3; produce manifest/raw outputs/claims annotations, metrics và FR matrix có evidence paths.

- [ ] Khóa shared split/gold/KB với nhóm còn lại; xác nhận approval/version và hashes trước run. Đọc CLI `--help` từng runner để dùng cờ thực tế, không tự chế tên flags.
- [ ] Chạy baseline truyền thống và model được chọn: 10-fold đủ 46 intent, mean/std/per-class/confusion; giữ holdout độc lập, không tune bằng test.
- [ ] Chạy retrieval gold + robustness/expired/conflict slices, Recall@3 ≥ 0,80; ghi denominator.
- [ ] Chạy LLM live trên dữ liệu giả lập sau khi môi trường sẵn sàng; lưu tokens/latency và draft/source snapshots đã mask; hai người chấm claim hoặc ghi rõ single-rater limit, adjudicate bất đồng. ≥ 90% claims supported là gate.
- [ ] Đo p50/p95 end-to-end, cold/warm, error rate, concurrency và average cost/request; p95 ≤ 12 giây. Không dùng latency mock làm live evidence.
- [ ] Tổ chức paired manual/copilot trên cùng nhóm yêu cầu, counterbalance thứ tự; lưu consent phù hợp, dữ liệu tổng hợp và approve/edit/reject/escalate. Nếu chưa có người tham gia: gate product value not_evaluated.
- [ ] Review mọi gate theo đề gốc; không đạt thì ghi fail/blocked kèm raw evidence, không chỉnh gold để đẹp số; commit report đã rà soát dữ liệu nhạy cảm.

## Task 6 — P1: Đồng bộ tài liệu và chốt bàn giao (0,5 ngày)

**Files:** `README.md`, `docs/CURRENT_LIMITATIONS.md`, `docs/product/requirements.md`, `docs/guides/application-verification.md`, `docs/README.md`, các README gateway/inference bị ảnh hưởng.

**Interfaces:** consume run evidence Task 5; produce một bản hướng dẫn tái lập và FR matrix nhất quán.

- [ ] Tách SQLite demo/eval khỏi PostgreSQL application; sửa 12 intent theo đề, default LLM và provenance model theo code sau sửa.
- [ ] Thay production-grade/zero hallucination bằng kết quả giới hạn đúng run/mẫu, link manifest; ghi gate chưa đánh giá và điều kiện chạy lại.
- [ ] Kiểm link, diff, không đưa credentials/PII vào docs; rerun suite liên quan sau thay đổi code cuối cùng. Tổng hợp review từng IMP-01…12 và FR-01…08.
- [ ] Review/commit phần tài liệu; bàn giao kết quả đạt/không đạt và công việc còn chặn. Người dùng đã ủy quyền triển khai; trạng thái thực tế ghi ở bảng đầu tài liệu.
