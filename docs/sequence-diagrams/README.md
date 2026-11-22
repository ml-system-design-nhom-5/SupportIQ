# Sequence Diagrams — Core Backend (SupportIQ)

Thư mục này chứa các biểu đồ tuần tự (Sequence Diagrams) mô tả chi tiết luồng xử lý của Core Backend, bám sát tài liệu kiến trúc [ARCHITECTURE.md](../ARCHITECTURE.md) và hợp đồng [core-backend.openapi.yaml](../api/core-backend.openapi.yaml).

## Danh mục biểu đồ

1. [01-ticket-intake-and-run-creation.md](./01-ticket-intake-and-run-creation.md) — Khách hàng tạo Ticket/Message và Nhân viên khởi tạo AI Run.
2. [02-ai-pipeline-and-safety-gates.md](./02-ai-pipeline-and-safety-gates.md) — AI Worker xử lý Pipeline (PII Sanitize, Phân loại Intent, Retrieval & Safety Gates).
3. [03-llm-egress-and-draft-validation.md](./03-llm-egress-and-draft-validation.md) — Egress Buffer gọi External LLM qua Proxy và Xác thực Draft.
4. [04-review-decision-and-reply-delivery.md](./04-review-decision-and-reply-delivery.md) — Nhân viên Kiểm duyệt (Review Decision) và Chủ động Gửi câu trả lời (Publish Reply).
