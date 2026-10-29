# 01. Tiếp nhận Ticket/Message và Khởi tạo AI Run

Tham chiếu đặc tả:
- [Mục 5.1 — Ticket, run và context](../superpowers/specs/2026-10-27-core-backend-design.md#51-ticket-run-và-context)
- [Mục 6.1 — Tiếp nhận và tạo draft (Bước 1–3)](../superpowers/specs/2026-10-27-core-backend-design.md#61-tiếp-nhận-và-tạo-draft)
- [Mục 8.2 — Các endpoint](../superpowers/specs/2026-10-27-core-backend-design.md#82-các-endpoint)

```mermaid
sequenceDiagram
    autonumber
    actor Customer
    actor Staff as Staff (Agent / Manager)
    participant API as Core API
    participant Redis as Redis Cache
    participant DB as PostgreSQL (app / audit)
    participant WS as WebSocket Gateway

    rect rgb(240, 248, 255)
    Note over Customer,WS: Bước 1: Khách hàng tạo Ticket hoặc gửi Message mới
    Customer->>API: POST /api/v1/tickets (hoặc /messages)<br/>Header: Idempotency-Key
    API->>API: Xác thực session, kiểm tra ownership order_id,<br/>validate giới hạn payload & mã hóa raw content
    API->>DB: BEGIN TRANSACTION
    DB->>DB: Lưu idempotency_records
    DB->>DB: INSERT tickets / messages (content_ciphertext)<br/>Tăng context_version & version, xóa current_decision_id<br/>Supersede active run cũ (nếu có)
    DB->>DB: INSERT audit.events (đã che PII)
    API->>DB: COMMIT
    API-->>Customer: 201 Created (kèm ETag mới, chưa gọi AI)
    API--)WS: Notify ticket.changed (best-effort)
    WS--)Staff: Frame {event: "ticket.changed", resource_id, version}
    end

    rect rgb(245, 255, 245)
    Note over Staff,WS: Bước 2: Nhân viên chủ động yêu cầu chạy AI
    Staff->>API: POST /api/v1/tickets/{ticket_id}/runs<br/>Header: Idempotency-Key, If-Match
    API->>DB: Kiểm tra RBAC, assignment & session/role_version
    API->>DB: Kiểm tra Idempotency-Key (trước ETag)
    API->>API: Kiểm tra ETag (ticket.version) & active release_manifest
    API->>Redis: Kiểm tra distributed rate limit & concurrency limit
    alt Rate limit vượt ngưỡng hoặc Redis lỗi
        Redis-->>API: Chặn (Fail-closed cho AI)
        API-->>Staff: 429 Too Many Requests / 503 Service Unavailable
    else Hợp lệ
        API->>DB: BEGIN TRANSACTION (Lock ticket)
        DB->>DB: Đánh dấu run cũ (nếu đang chạy) = superseded
        DB->>DB: INSERT pipeline_runs (status=queued, ghim manifest_id, deadline_at)
        DB->>DB: INSERT jobs (stage=pipeline, status=queued)
        DB->>DB: UPDATE tickets (current_run_id, xóa current_decision_id, tăng version)
        DB->>DB: INSERT audit.events
        API->>DB: COMMIT
        API-->>Staff: 202 Accepted (Location: /api/v1/runs/{run_id}, ETag mới)
        API--)WS: Notify run.changed & ticket.changed
    end
    end
```
