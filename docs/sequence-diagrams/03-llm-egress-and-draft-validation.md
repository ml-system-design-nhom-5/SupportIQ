# 03. Egress Buffer gọi External LLM & Xác thực Draft

Tham chiếu:
- Kiến trúc tổng quan: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Quyết định kiến trúc: [ADR-0006 LLM Egress Isolation](../decisions/0006-llm-egress-isolation.md)
- Luồng xử lý: Egress Proxy allowlist, gọi External LLM, và xác thực Draft grounding/evidence

```mermaid
sequenceDiagram
    autonumber
    participant Egress as AI Worker (Egress)
    participant DB as PostgreSQL (app / audit)
    participant Proxy as Egress Proxy (Allowlist)
    participant LLM as External LLM
    participant WS as WebSocket Gateway
    actor Staff as Staff (Agent / Manager)
    participant API as Core API

    Egress->>DB: Claim job (stage=llm_egress) bằng row lock (lease_token mới)
    Egress->>DB: Kiểm tra còn ngân sách (deadline_at) & run chưa bị superseded
    Egress->>DB: INSERT llm_attempts (attempt_no, state=in_flight)

    Egress->>Proxy: Gửi request đã sanitized (timeout = min(8s, remaining_budget))
    Proxy->>Proxy: Kiểm tra domain allowlist, chặn redirect/telemetry/log nhạy cảm
    Proxy->>LLM: HTTPS POST (chỉ payload đã che PII)

    alt Timeout / Lỗi mạng / Outcome không rõ
        LLM--xProxy: Timeout hoặc lỗi kết nối
        Proxy-->>Egress: Lỗi downstream
        Egress->>Egress: Chỉ retry (tối đa 2 lần) nếu chắc chắn chưa gửi<br/>hoặc có idempotency key được provider hỗ trợ và còn deadline
        Egress->>DB: TX: UPDATE llm_attempts (state=outcome_unknown / failed)<br/>UPDATE pipeline_runs (status=escalated, reason=llm_unavailable/pipeline_timeout, cost=unknown)<br/>UPDATE tickets (manual_required=true) + INSERT audit.events
        Egress--)WS: Notify run.changed
    else Nhận được phản hồi từ LLM
        LLM-->>Proxy: JSON Response {body, citation_ids, usage}
        Proxy-->>Egress: Trả response
        Egress->>Egress: Validate schema {body, citation_ids},<br/>mọi citation_id thuộc evidence_snapshots của run,<br/>không có URL/tool call lạ, quét PII scanner đầu ra

        alt Output vi phạm contract / thiếu citation / dính PII
            Egress->>DB: TX: UPDATE llm_attempts (state=completed, usage/cost)<br/>UPDATE pipeline_runs (status=escalated, reason=invalid_llm_output)<br/>UPDATE tickets (manual_required=true) + INSERT audit.events
            Egress--)WS: Notify run.changed
        else Output hợp lệ
            Egress->>DB: BEGIN TRANSACTION (Kiểm tra lease_token & run chưa superseded)
            alt Run đã bị superseded trong lúc chờ LLM
                DB->>DB: Chỉ lưu llm_attempts + trace kỹ thuật vào audit.events<br/>(Không công bố draft)
            else Run vẫn là current_run_id
                DB->>DB: INSERT drafts (bất biến: run_id, sanitized_body, citation_ids)
                DB->>DB: UPDATE llm_attempts (state=completed, token_usage, cost)
                DB->>DB: UPDATE pipeline_runs (status=awaiting_review, latency)
                DB->>DB: INSERT audit.events
            end
            Egress->>DB: COMMIT
            Egress--)WS: Notify run.changed
            WS--)Staff: Frame {event: "run.changed", resource_id: run_id}
            Staff->>API: GET /api/v1/runs/{run_id}
            API-->>Staff: Trả draft, evidence_snapshots, predicted_intent, confidence, warnings
        end
    end
```
