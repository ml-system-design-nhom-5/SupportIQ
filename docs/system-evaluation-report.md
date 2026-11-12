# Báo cáo kiểm chứng SupportIQ sau xử lý 8 vấn đề review

Trạng thái: **chưa chứng nhận nghiệm thu**. Các sửa đổi kỹ thuật được kiểm tra bằng regression/probe; chưa chạy lại benchmark live sau sửa và chưa có user study mới.

## 1. Những gì đã sửa

| Vấn đề review | Thay đổi | Phạm vi bằng chứng |
| --- | --- | --- |
| Worker ghi muộn sau timeout | Công việc thực thi trong process riêng; deadline terminate/join đúng process. Live quality đi vào worker qua HTTP nội bộ có nonce | Native SQLite probe khóa DB, timeout, mở khóa và kiểm tra không có late write |
| Dev/acceptance trùng | Tạo benchmark v3: dev 50 case theo đúng quotas; acceptance 156 câu mới, kiểm tra overlap normalized text với dev/v1 | Bộ v1/v2 giữ nguyên làm lịch sử; v3 vẫn draft, chưa có người duyệt ngữ nghĩa hoặc chứng nhận đánh giá mù |
| ML metrics chưa xác minh | Descriptor khóa checksum release, mọi artifact, report và 10 fold; không nhận inline scores/candidate như verified | CV report thực của `supportiq_distilbert`, không dùng điểm fixture |
| Mất evidence đơn hàng | Snapshot sanitized prompt và policy/order sources được lưu trước egress; result/export giữ excerpt/hash/citation | Truy vết snapshot cho cả attempt lỗi; dữ liệu business giả lập và allowlist |
| KB v2 chưa được dùng | Runtime mặc định v2; manifest benchmark v3 pin v2 | Metadata hiện có tự khai approval; không coi đây là chứng nhận mới của giảng viên |
| HTTP pooling chưa nối | Client mặc định thực sự tái sử dụng pool; client sở hữu được đóng khi shutdown | Test hai call chỉ tạo một pool; không suy ra latency cải thiện từ test |
| Human review thiếu metadata | Bắt buộc actor human explicit, timestamp có timezone, attestation, relevance; supported claim cần citation và evidence version | AI không được mặc định thành human; fixture kiểm tra công thức khai báo rõ dữ liệu tổng hợp |
| Báo cáo có số liệu thiếu nguồn | Gỡ các kết luận `40/40`, `1,00`, `5/5`, `0,885` chưa có artifact benchmark đúng scope | Phân biệt code test, dữ liệu historical và acceptance chưa chạy |

## 2. ML CV có bằng chứng local

Descriptor: [cv_metrics.json](../ml/releases/cv_metrics.json). CV Macro-F1 trong report thật là **0,9952684306823985**, 10-fold cross-validation, `supportiq_distilbert` release `v1.0.0`.

Importer kiểm tra checksum release/model/tokenizer/config/training report, đủ mười fold duy nhất, score hữu hạn, protocol và trung bình các fold. Đây là xác minh nhất quán artifact local, không phải chữ ký của người phê duyệt, chạy lại training hay tái lập độc lập kết quả CV. Không dùng 0,885 từ unit-test fixture làm số liệu sản phẩm.

## 3. Benchmark mới và KB

- [Dev v3](../data/benchmarks/system/v3/dev/suite_manifest.json): 50 case, quotas 20 supported / 10 unsupported / 10 answerable / 5 unanswerable / 5 uncertainty-faults; chỉ dùng phát triển/chẩn đoán.
- [Acceptance v3](../data/benchmarks/system/v3/acceptance/suite_manifest.json): 156 case với câu chữ mới, không trùng normalized text của dev/v1; gold và coverage cần người duyệt.
- Manifest acceptance khóa hash dev/retired cases; loader từ chối overlap và quota sai. Không khẳng định việc đổi câu chữ tự bảo đảm tính độc lập thống kê hoặc đủ khả năng bao phủ nghiệp vụ.
- Runtime và v3 dùng `data/knowledge/approved_kb.v2.json`. Không chỉnh KB/gold theo output để đạt điểm. Metadata approval có trong KB là dữ liệu cung cấp sẵn, không thay cho quy trình xác nhận nguồn thực.

## 4. Các phép đo lịch sử — không áp dụng làm pass cho phiên bản mới

| Chỉ số | Giá trị lịch sử | Trạng thái hiện tại |
| --- | --- | --- |
| Routing E2E | 31/63 case must-escalate trong run cũ | Chưa đo lại sau sửa |
| Retrieval E2E Recall@3 | 61,76% trong run cũ | Chưa đo lại với v3/KBv2 |
| HTTP demo p95 toàn bộ | 10,68 giây /100 request | Lần đo cũ, không dùng chứng nhận hiệu năng code mới |
| HTTP nhánh LLM p95 | 15,31 giây | Cần đo lại, không được ẩn sau p95 chung |
| Oversight live | 3/4 scenario trong run cũ | Test đúng hành vi không thay benchmark mới |

[Xem báo cáo lịch sử HTTP và grounding](../artifacts/evaluation/05-11-2026-system-http-assessment-00/report.md). Artifact cũ giữ nguyên; khi chạy mới phải dùng run ID mới và không ghi đè.

## 5. Grounding đã được người dùng duyệt

Người dùng xác nhận **“Tôi duyệt grounding”** đối với phiếu cũ: 13 draft, 17 claim, 15 supported, 2 unknown, tỷ lệ quan sát **88,24%**. [Biên bản](../artifacts/evaluation/grounding-approvals/user-grounding-approval-001/approval.json).

Không chuyển hai unknown thành supported. Do còn 28 case kỳ vọng chưa sinh draft, grounding toàn bộ run cũ vẫn `insufficient_evidence`; tỷ lệ quan sát cũng dưới mục tiêu 90%. Việc duyệt chỉ có hiệu lực với draft/hash cũ, không tự áp dụng cho prompt/model/KB mới. Snapshot evidence mới giải quyết khả năng truy vết cho các lần chạy sau, không hồi tố tạo bằng chứng đơn hàng bị thiếu của lần cũ.

## 6. Hợp đồng FR và việc còn lại

Đối chiếu đúng mã yêu cầu trong [đề bài](CHỦ%20ĐỀ%201.md): FR-01 intent; FR-02 retrieval/thiếu-cũ-mâu thuẫn; FR-03 draft grounded; FR-04 human review; FR-05 fallback/escalation; FR-06 quyền quyết định nghiệp vụ; FR-07 audit/feedback/version; FR-08 lỗi/phân quyền/bảo vệ dữ liệu. Không đổi tên các mã để thay thế yêu cầu ban đầu.

Trước nghiệm thu cần: người phụ trách duyệt gold/KB v3; benchmark live mới đủ mẫu có ngân sách; người chấm duyệt claim mới; user study paired manual/copilot thật. Chưa hoàn tất những bước này thì không ghi “implementation 100% đồng nghĩa hệ thống đạt toàn bộ chỉ tiêu”.

## 7. Vận hành

```powershell
.venv\Scripts\python.exe -m uvicorn apps.demo.app:create_app --factory --host 127.0.0.1 --port 8000
```

Giao diện ở `http://127.0.0.1:8000/`. Server ML dùng `apps.ml_inference.app:app` tại8001. Benchmark mock mới:

```powershell
.venv\Scripts\python.exe -m pipeline.evaluation.run_system_evaluation --suite data/benchmarks/system/v3/dev/suite_manifest.json --config pipeline/configs/system_evaluation.dev.json --profile mock
```

Mock là simulated evidence, không chứng minh chất lượng BGE/Gemini thật. Escalation lưu trong bảng `escalation_queue` của orchestration SQLite; feedback lưu trong `demo_feedback` của demo SQLite.

## 8. Kiểm chứng sau sửa

- Regression cuối: **382 passed**, 86 cảnh báo deprecation, 158,19 giây.
- Lệnh: `.venv\Scripts\python.exe -m pytest tests/unit tests/integration --basetemp=.pytest-eight-release-check -k "not test_gemini_live" -q`.
- Probe native SQLite không late write, CV checksum/tampering, actor metadata, actual pooling và managed HTTP worker đều đạt.
- Mock smoke dev v3: 50/50 kết quả, không lỗi thực thi/thiếu output; checksum15 artifact được xác minh. Đây là bằng chứng simulated, không thay benchmark live.
- `git diff --check` sạch; artifact lịch sử và biên bản duyệt grounding cũ đã kiểm tra checksum, không thay đổi.
- [Biên bản sửa 8 vấn đề](review-eight-fixes.md). Chưa commit/push; không gọi API LLM trả phí trong đợt sửa. Acceptance v3 và benchmark live mới vẫn là bước nghiệm thu riêng.
