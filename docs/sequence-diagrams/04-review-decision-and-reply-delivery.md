# 04. Nhân viên Kiểm duyệt (Review Decision) & Chủ động Gửi trả lời (Publish Reply)

Tham chiếu đặc tả:
- [Mục 3 — Bất biến bắt buộc](../superpowers/specs/2026-10-27-core-backend-design.md#3-bất-biến-bắt-buộc)
- [Mục 5.2 — Quyết định kiểm duyệt và gửi trả lời](../superpowers/specs/2026-10-27-core-backend-design.md#52-quyết-định-kiểm-duyệt-và-gửi-trả-lời)
- [Mục 7.1 — Transaction và đồng thời](../superpowers/specs/2026-10-27-core-backend-design.md#71-transaction-và-đồng-thời)

```mermaid
sequenceDiagram
    autonumber
    actor Staff as Staff (Agent / Manager)
    participant API as Core API
    participant DB as PostgreSQL (app / knowledge / audit)
    participant WS as WebSocket Gateway
    actor Customer

    rect rgb(255, 250, 240)
    Note over Staff,DB: Pha 1: Ghi quyết định kiểm duyệt (Approve / Edit / Reject / Escalate / Manual)
    Staff->>API: POST /api/v1/tickets/{ticket_id}/decisions<br/>Header: Idempotency-Key, If-Match<br/>Body: {action, source, run_id?, final_body?, final_intent, reason?}
    API->>DB: Kiểm tra RBAC, queue scope & session/role_version trực tiếp từ DB
    API->>DB: Kiểm tra Idempotency-Key
    API->>DB: BEGIN TRANSACTION (Lock theo thứ tự: ticket -> run)
    API->>API: Kiểm tra ETag (ticket.version) & context_version khớp
    API->>API: Chạy rule nhạy cảm trên final_intent & nội dung;<br/>Kiểm tra không còn token placeholder chưa giải;<br/>Nếu AI approve/edit: kiểm tra final_intent khớp run & evidence còn hiệu lực

    alt Vi phạm điều kiện (placeholder còn sót, khác intent, evidence hết hạn...)
        API->>DB: ROLLBACK
        API-->>Staff: 409 Conflict (state_conflict / evidence_changed) hoặc 412 Precondition Failed
    else Hợp lệ
        DB->>DB: INSERT review_decisions (bất biến, mã hóa final_body_ciphertext)
        alt action == approve hoặc edit
            DB->>DB: UPDATE tickets SET current_decision_id = decision.id, tăng version<br/>(Nếu source=manual: supersede active run, tăng context_version nếu đổi intent)
        else action == reject hoặc escalate
            DB->>DB: UPDATE tickets SET current_decision_id = NULL, manual_required = true,<br/>(Nếu escalate: handling_queue = manager, dừng active run), tăng version
        end
        DB->>DB: INSERT audit.events (đã che PII, lưu content hash)
        API->>DB: COMMIT
        API-->>Staff: 201 Created (Trả decision + ETag mới; CHƯA gửi cho khách)
        API--)WS: Notify ticket.changed
    end
    end

    rect rgb(240, 255, 245)
    Note over Staff,Customer: Pha 2: Nhân viên chủ động bấm Gửi câu trả lời (Chỉ áp dụng cho decision approve/edit)
    Staff->>API: POST /api/v1/tickets/{ticket_id}/replies<br/>Header: Idempotency-Key, If-Match<br/>Body: {decision_id}
    API->>DB: Kiểm tra RBAC, assignment & session/role_version trực tiếp từ DB
    API->>DB: Kiểm tra Idempotency-Key
    API->>DB: BEGIN TRANSACTION (Lock theo thứ tự: ticket -> run -> decision)
    API->>DB: Kiểm tra: ETag khớp, ticket.current_decision_id == decision_id,<br/>decision.action IN (approve, edit), decision chưa có reply,<br/>context_version khớp, knowledge evidence & business snapshot version còn hiệu lực

    alt Nguồn dữ liệu / đơn hàng đã thay đổi hoặc decision không còn hiện hành
        API->>DB: ROLLBACK (Giữ nguyên decision cũ để truy vết)
        API-->>Staff: 409 Conflict (evidence_changed / state_conflict)
    else Hợp lệ
        DB->>DB: INSERT replies (ticket_id, decision_id unique, final_body_ciphertext)
        DB->>DB: UPDATE tickets SET status = resolved, current_decision_id = NULL, tăng version
        DB->>DB: INSERT audit.events (cùng transaction, thiếu audit thì rollback)
        API->>DB: COMMIT
        API-->>Staff: 201 Created (Reply đã công bố, kèm ETag mới)
        API--)WS: Notify ticket.changed
        WS--)Customer: Frame {event: "ticket.changed", resource_id: ticket_id}
        Customer->>API: GET /api/v1/tickets/{ticket_id}/messages
        API-->>Customer: 200 OK (Hiển thị câu trả lời đã giải mã của Staff)
    end
    end
```
