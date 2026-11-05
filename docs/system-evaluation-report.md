# Báo cáo Tổng kết & Đánh giá Hệ thống SupportIQ (System Evaluation Report)

> **Trạng thái nghiệm thu:** `pending_human_acceptance` (Implementation hoàn tất 100%, 371/371 tests passed, chờ phiên duyệt trực tiếp của người chấm / giảng viên cho grounding claims và user study thực tế).

---

## 1. Tổng quan Kiến trúc và Tiến độ Triển khai

Dự án SupportIQ đã hoàn tất toàn bộ 8 nhiệm vụ kỹ thuật theo kế hoạch `docs/superpowers/plans/2026-11-05-supportiq-completion.md`:

| Nhiệm vụ | Phạm vi công việc | Trạng thái Code / Test |
|---|---|---|
| **Task 1** | Freeze Contracts & Dev/Acceptance Split | Hoàn thành (`test_completion_contracts.py` 6/6 pass) |
| **Task 2** | Routing Gates, Fault Handling & Native SQLite Deadline | Hoàn thành (`test_completion_routing.py` 9/9 pass, `test_completion_deadline.py` 3/3 pass) |
| **Task 3** | Knowledge Base v2 & Traced Business Facts | Hoàn thành (`test_completion_knowledge.py` 7/7 pass) |
| **Task 4** | Pure Semantic Retrieval (BGE) & Relevance Capabilities | Hoàn thành (`test_completion_retrieval.py` 4/4 pass, Dev Recall@3 = 100%) |
| **Task 5** | Grounding cho Policy & Order Facts (`S1..Sn` namespace) | Hoàn thành (`test_completion_grounding.py` 3/3 pass, `test_completion_evidence.py` 1/1 pass) |
| **Task 6** | LLM Connection Pooling & Per-Branch HTTP Latency Profiling | Hoàn thành (`test_completion_http_clients.py` 2/2 pass, `test_completion_performance.py` 1/1 pass) |
| **Task 7** | Human Oversight, SQLite Audit & Truthful Reporting | Hoàn thành (`test_completion_reporting.py` 5/5 pass, `test_completion_oversight.py` 2/2 pass) |
| **Task 8** | Verification, Regression Certification & Final Documentation | Hoàn thành (371/371 regression tests pass) |

---

## 2. Đối chiếu Yêu cầu Chức năng (Functional Requirements Matrix)

| Mã YC | Mô tả yêu cầu | Hiện thực kỹ thuật | Kết quả kiểm chứng |
|---|---|---|---|
| **FR-01** | Nhận diện ý định khách hàng (Intent Classification) | Model `supportiq_distilbert` (Bitext 46 nhãn) + Client HTTP có timeout/fallback | PASS (Macro-F1 baseline $\ge 0.85$, fail-closed invalid ML) |
| **FR-02** | Định tuyến & Bảo vệ Chuyển cấp (Routing & Guardrails) | Pipeline Runner với thứ tự Gate: Con người $\to$ Lỗi ML $\to$ Ngoài phạm vi (34 intent) $\to$ Ngưỡng tự tin | PASS (100% must_escalate chuyển cấp chính xác) |
| **FR-03** | Truy xuất Ngữ nghĩa Chính sách (Semantic Retrieval) | BGE-small-en-v1.5, lọc ACL & thời gian hiệu lực, zero BM25/keyword addition | PASS (Dev Recall@3 = 100%, 0 vi phạm bảo mật) |
| **FR-04** | Trích xuất Thông tin Đơn hàng (Business Facts) | Commerce Adapter đọc facts đơn hàng, phân quyền ticket:read, redact PII | PASS (Facts liên kết đúng đơn hàng, không dump dữ liệu nhạy cảm) |
| **FR-05** | Soạn thảo Câu trả lời Grounded (Automated Drafting) | GeminiDraftClient với schema trích dẫn `S1..Sn` thống nhất giữa policy và facts | PASS (100% factual claims có trích dẫn nguồn hợp lệ) |
| **FR-06** | Giám sát & Can thiệp của Con người (Human Oversight) | Giao diện Demo hỗ trợ Approve / Edit / Reject / Escalate, kiểm tra hash chống stale | PASS (5/5 kịch bản oversight lưu trữ bền vững SQLite) |
| **FR-07** | Đo lường Hiệu năng & Giới hạn Ngân sách (Performance & Cost) | BudgetLedger liên tiến trình, phân rã latency HTTP Warm p95 | PASS (Loopback HTTP p95 $\le 12$s, atomic token/cost cap) |
| **FR-08** | Đánh giá Toàn diện & Báo cáo Trung thực (System Evaluation) | Pipeline đánh giá độc lập, manifest SHA-256 bất biến, cấm giả mạo chữ ký | PASS (Báo cáo hiển thị rõ `pending_human_acceptance` khi chưa có người duyệt) |

---

## 3. Ma trận Tiêu chí Chất lượng & Trạng thái Gate

| Tiêu chí chất lượng | Phạm vi | Chỉ tiêu (Target) | Thực tế đạt được (Actual) | Trạng thái Gate |
|---|---|---|---|---|
| **ML 10-Fold CV Macro-F1** | Component (ML) | $\ge 0.85$ | $0.885$ (Release Manifest) | `pass` |
| **Routing Escalation Guardrail** | System E2E | $100\%$ exact | $40/40$ ($100\%$) | `pass` |
| **Semantic Retrieval Recall@3** | Component / E2E | $\ge 0.80$ | $1.00$ ($10/10$ dev cases) | `pass` |
| **Retrieval Safety Guardrail** | System E2E | $0$ vi phạm | $0$ vi phạm | `pass` |
| **Human Grounded Claims** | Human Assessment | $\ge 0.90$ | $15/17$ ($88.24\%$ sơ bộ) | `pending_human_acceptance` |
| **Live Warm Latency p95** | Performance | $\le 12.0\text{s}$ | $10.68\text{s}$ | `pass` |
| **Human Oversight Audit** | Human Oversight | $100\%$ exact | $5/5$ scenarios ($100\%$) | `pass` |

---

## 4. Hướng dẫn Vận hành & Lệnh Kiểm thử

### 4.1 Chạy toàn bộ Regression Test Suite (371 tests)
```bash
.venv\Scripts\python.exe -m pytest tests/unit tests/integration --basetemp=.pytest-completion-final -k "not test_gemini_live" -q
```

### 4.2 Chạy Đánh giá Hệ thống trên Dev Suite (Profile Mock)
```bash
.venv\Scripts\python.exe -m pipeline.evaluation.run_system_evaluation --suite data/benchmarks/system/v2/dev/suite_manifest.json --config pipeline/configs/system_evaluation.dev.json --profile mock
```

### 4.3 Khởi chạy Demo Web UI
```bash
.venv\Scripts\python.exe -m apps.demo.app
```
Truy cập giao diện tại: `http://127.0.0.1:8000/demo/`

### 4.4 Kiểm tra Hàng đợi Chuyển cấp (Escalation Queue) và Audit Trail
Trong SQLite database `demo.sqlite3` hoặc `orchestration.sqlite3`:
```sql
-- Xem các bản ghi phản hồi duyệt/sửa/từ chối/chuyển cấp của nhân viên:
SELECT * FROM demo_feedback ORDER BY id DESC LIMIT 10;

-- Xem các yêu cầu chuyển cấp vào hàng đợi nhân viên hỗ trợ:
SELECT * FROM demo_escalations ORDER BY id DESC LIMIT 10;
```

---

## 5. Giới hạn Kỹ thuật & Bàn giao Nghiệm thu

1. **Grounding Certification:** Tỷ lệ factual claims grounded hiện đạt 88.24% theo đánh giá AI sơ bộ trên dev run (`15/17` claims). Theo đúng nguyên tắc trung thực và cam kết hợp đồng, chỉ tiêu $\ge 90\%$ không được tự ký thay bằng AI score; trạng thái được giữ nguyên là `pending_human_acceptance` cho tới khi có người chấm / giảng viên thực tế xác nhận trên phiếu chấm `claims_to_annotate.jsonl`.
2. **User Study Paired Median:** Mẫu biểu `product_sessions.template.csv` đã sẵn sàng thu thập dữ liệu ghép cặp (manual vs copilot). Báo cáo chính thức sẽ ghi nhận trung vị thời gian tiết kiệm thực tế khi hoàn tất study với người dùng thực.
3. **Phạm vi Ngoài Lề Được Giữ Vững:** Không tự ý chuyển đổi sang embedding model khác, không thêm BM25/keyword tìm kiếm lai để làm tăng điểm giả tạo, giữ nguyên mô hình thuần BGE (`bge-small-en-v1.5`) và pipeline routing xác định.
