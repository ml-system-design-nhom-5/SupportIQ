# Review và chạy thử SupportIQ theo Chủ đề 1

Ngày: 2026-11-12. Commit được review: `5e0cda5cb24a79ff2d6892ab7abf611c3da054d5`.

Nguồn yêu cầu cao nhất: [CHỦ ĐỀ 1](../CHỦ%20ĐỀ%201.md). Đây là review prototype, không phải chứng nhận production. Chỉ thêm tài liệu, không sửa chương trình. Các file PPTX và `tests/unit/test_retry_draft.py` đã untracked trước khi review, được giữ nguyên; test untracked vẫn thuộc phạm vi lệnh pytest toàn bộ.

## 1. Kiến trúc được kiểm tra

`apps/frontend` (React/TypeScript) → `apps/backend` (FastAPI, session, RBAC, ticket, audit, PostgreSQL) → `apps/ai_service` (HTTP stateless) → `apps/ml_inference` + retrieval/LLM trong `apps/core_backend`.

`apps/demo` và pipeline đánh giá là các đường chạy riêng. Không lấy SQLite của demo/evaluation làm bằng chứng database của ứng dụng chính. Không có `.codegraph/` tại root; không dùng CodeGraph. `rg` không có trong shell nên dùng PowerShell để đọc và tìm mã.

## 2. Phát hiện theo mức ưu tiên

### R01 — Cao: fallback heuristic mang danh tính model thật

Vị trí: `apps/ml_inference/app.py`, `ModelContainer.load`, `is_ready`, `predict`.

Khi thư mục model tồn tại nhưng thiếu weights/tokenizer/config, biến `SUPPORTIQ_DEV_FALLBACK_MODEL` mặc định `true`. Nhánh fallback gán `verified_model_version`, checksum weights và tokenizer từ manifest, tạo `object()` thay cho model/tokenizer và dựng đủ 46 nhãn. `is_ready()` chỉ kiểm tra các trường này và bijection nhãn nên có thể trả true. `predict()` dùng regex và xác suất định sẵn nhưng trả danh tính/checksum của artifact thật; khi yêu cầu calibrated còn trả `calibrated_probability`.

Hệ quả: demo hoặc benchmark có thể nhận nhầm heuristic là ML đã huấn luyện, trái mục tiêu FR-01 và làm mất tính truy vết. Chỉ xảy ra với thư mục có sẵn nhưng thiếu file; thư mục hoàn toàn không tồn tại thì load trả về trước fallback.

Đã tái hiện bằng cách trích nguyên AST class `ModelContainer` từ source, cung cấp globals chuẩn và stub `PredictionItem`, tạo instance bằng `__new__` để không import PyTorch/Transformers, gọi `load()` với thư mục tạm rỗng rồi `predict()`. Không sửa logic class; không thực hiện inference model thật. Kết quả: `ready=true`, `heuristic=true`, version `v1.0.0`, checksum khớp manifest thật dù thư mục rỗng; câu “Where is my order?” trả `track_order`, confidence `0.94`; `calibrated=True` trả `calibrated_probability`. Đây là tái hiện logic cô lập, không phải test tích hợp gateway.

Đề xuất: mặc định fail closed; fallback chỉ bật tường minh cho demo, có identity riêng, không checksum artifact thật, không được tham gia nghiệm thu ML.

### R02 — Cao: không thể khởi động ứng dụng trên môi trường hiện tại

Lệnh `./scripts/start-app.ps1 -SkipInstall -SkipBuild -DisableLLM` dừng tại `scripts/native_runtime.py:47`, lúc import psycopg, trước khi chạy ứng dụng. Lỗi: `no pq wrapper available`; `psycopg_binary` bị `An Application Control policy has blocked this file`, bản C không cài và bản Python không tìm thấy libpq.

Đây là lỗi môi trường phụ thuộc native, không chứng minh lỗi nghiệp vụ hoặc thiếu Python. Không đổi chính sách bảo vệ Windows để chạy thử. Cần dùng dependency được máy cho phép hoặc môi trường được quản trị phê duyệt, rồi chạy lại startup, DB integration và E2E. Không công bố E2E pass từ số liệu cũ.

### R03 — Cao: bằng chứng nghiệm thu chưa thống nhất

`artifacts/evaluation/acceptance-eval-001/report.md` tự ghi `simulated_mock_rejected`, Recall@3 0.4118, routing 18/63, thiếu annotation và chưa import ML benchmark. Trong khi `artifacts/evaluation/regression/REGRESSION_REPORT.md` ghi Recall@3 0.9706, grounding 1.0 từ nguồn khác. Hai run khác nhau không đủ để kết luận regression của cùng cấu hình, cũng không được chọn số tốt hơn làm kết quả nghiệm thu.

`scripts/evaluate_regression.py` có đường đọc summary có sẵn và thay metric thiếu bằng 0 trong `extract_metrics`. Metric dạng upper-bound như hallucination có thể vì vậy trông đạt dù không đo. Cần trạng thái `not_evaluated/insufficient_evidence`, manifest/hash và đường dẫn provenance cho từng metric. Report mới tạo không đồng nghĩa inference mới chạy.

### R04 — Vừa: tài liệu và runtime không khớp

`docs/CURRENT_LIMITATIONS.md` mô tả SQLite cho ứng dụng, danh sách 12 intent không đúng đề và tuyên bố production-grade/zero hallucination quá phạm vi bằng chứng. README nói raw-score/model-verified nhưng code mới đã có fallback và tùy chọn calibration. Docstring `apps/ai_service/main.py` nói LLM disabled mặc định trong khi `AiSettings.supportiq_enable_llm=True` và script startup bật trừ khi `-DisableLLM`.

Cần tách tài liệu application, legacy demo, simulated evaluation; ghi giới hạn mẫu và không biến kết quả mẫu thành bảo đảm tổng quát.

### R05 — Vừa: citation có tồn tại chưa chứng minh claim đúng

`Engine.draft` kiểm source ID/placeholder và chặn paragraph dài hơn 40 ký tự thiếu citation. Paragraph ngắn có thể không citation khi đoạn khác có nguồn; citation hợp lệ cũng có thể gắn với câu sai nội dung. Human review vẫn bắt buộc. Cần benchmark claim-level có annotation độc lập, bao gồm câu ngắn chứa tiền/thời hạn, nguồn thật nhưng không hỗ trợ kết luận, và mâu thuẫn nguồn.

### R06 — Cần làm rõ: test retry nằm ngoài git

`tests/unit/test_retry_draft.py` kỳ vọng retry khi `draft_ready`, nhưng `allowed_actions()` chỉ cấp retry cho `unavailable`/`llm_unavailable`. Đây là chênh lệch kỳ vọng/code, chưa xác định là bug nghiệp vụ: đề bài không buộc regenerate bản nháp đã sẵn sàng. Chốt policy rồi mới sửa test/code, không tự thay đổi hành vi.

## 3. Đối chiếu yêu cầu gốc

| Yêu cầu | Cơ sở trong code | Khoảng trống cần nghiệm thu |
|---|---|---|
| FR-01 | ModelContainer; intent/score/override ở Engine | R01; baseline và 10-fold trên đủ 46 nhãn chưa tái chạy |
| FR-02 | retrieval theo intent, as_of, conflict/no_valid_document | Chạy lại recall trên KB/gold đã khóa phiên bản |
| FR-03 | LLM + sources, segments/citations/placeholder checks | Đánh giá claim thực tế, không chỉ source ID |
| FR-04 | ticket actions/send/proposal, phân quyền | E2E nhân viên gửi và khách chỉ thấy reply đã gửi |
| FR-05 | low confidence, OOD, human_agent, conflict, unavailable | Fault injection và toàn bộ escalation suite |
| FR-06 | requires_authority, sticky authority, manager flow | Hoàn tiền/chargeback không tự thực hiện giao dịch |
| FR-07 | audit, suggestion versions, reporting | Kiểm chứng persistence/immutability bằng PostgreSQL |
| FR-08 | session/RBAC/Origin/idempotency; pseudonymization | DB isolation và kiểm tra payload/log thực tế |

`docs/product/requirements.md` có số FR mở rộng; bảng trên luôn dùng số FR trong đề gốc để tránh nhập nhằng.

## 4. Kết quả chạy mới

| Lệnh / phạm vi | Kết quả phiên 12-11 | Giới hạn |
|---|---|---|
| `.venv/Scripts/python.exe -X utf8 -m pytest -q` | Không ra kết quả sau nhiều phút; chủ động dừng bằng Ctrl+C, exit 1 | Không có counts/pass/fail; chưa xác định vị trí treo |
| `pytest --collect-only -q` qua Python wrapper `faulthandler.dump_traceback_later(20, exit=True)` | Exit 1, không có collection summary/trace được trả về | Diagnostic chưa xác định nguyên nhân; không khẳng định lỗi assertion hoặc toàn bộ tests fail |
| `pnpm build` tại `apps/frontend` | TypeScript + Vite thành công; 2.177 modules, Vite build 58,67 giây | Không chứng minh backend/runtime hoạt động |
| `pnpm test -- --run` tại frontend | Exit 1; 2 unhandled errors, fork workers timeout, không test nào chạy | Không phải lỗi assertion nghiệp vụ |
| `pnpm exec vitest run --pool=threads --maxWorkers=1` tại frontend | Exit 0; **2 test files, 11 tests passed**, 53,81 giây | Cấu hình pool khác mặc định; không sửa config repository |
| `./scripts/start-app.ps1 -SkipInstall -SkipBuild -DisableLLM` | Exit 1 vì driver PostgreSQL/DLL, chi tiết R02 | Backend/AI chưa được startup bằng lệnh này |
| AST isolated `ModelContainer.load/predict` | Exit 0; tái hiện R01 | Không tải weights và không gọi provider |
| E2E / live LLM / training / benchmark đầy đủ | Chưa chạy | Startup bị chặn; không có kết quả nghiệm thu mới |

Python stdlib chạy được trong venv (`ast.parse` thành công); vấn đề không phải máy không có Python. Không dùng kết quả 419 tests/8 E2E từ ngày 05-11 làm kết quả của phiên này. Không tự sửa driver, bypass Windows policy hoặc thay database trong phạm vi review.

Để tái lập R01: parse `apps/ml_inference/app.py` bằng `ast`, lấy `EXPECTED_MANIFEST`/`EXPECTED_46_LABELS` bằng `ast.literal_eval`, compile riêng class, dùng globals `typing`, `Path`, `logger`, `hashlib`, `json`, `MODEL_DIR` và `PredictionItem=lambda **kw: SimpleNamespace(**kw)`. Instance khởi tạo qua `__new__`, set model/tokenizer/version=None, id2label={}, rồi load thư mục `TemporaryDirectory` và gọi predict như trên. Mục đích chỉ kiểm đường fallback độc lập native dependencies.

## 5. Khuyến nghị

Giữ kiến trúc hiện có, ưu tiên sửa provenance model, khôi phục môi trường chạy và chuẩn hóa bằng chứng trước khi tối ưu metric. Mở rộng bán hàng, production hosting hoặc thay toàn bộ stack không cần để đáp ứng Chủ đề 1. Xem [đặc tả](../superpowers/specs/2026-11-12-topic-1-improvements-design.md) và [kế hoạch](../superpowers/plans/2026-11-12-topic-1-improvements.md).
