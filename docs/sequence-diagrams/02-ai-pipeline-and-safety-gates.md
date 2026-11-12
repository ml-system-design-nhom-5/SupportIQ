# 02. AI Worker xử lý Pipeline (Sanitize, Intent, Retrieval & Safety Gate)

Tham chiếu đặc tả:
- [Mục 6.1 — Tiếp nhận và tạo draft (Bước 4–9)](../superpowers/specs/2026-10-27-core-backend-design.md#61-tiếp-nhận-và-tạo-draft)
- [Mục 6.2 — Phạm vi intent và chuyển cấp](../superpowers/specs/2026-10-27-core-backend-design.md#62-phạm-vi-intent-và-chuyển-cấp)
- [Mục 9.1–9.3 — Hợp đồng AI, evidence và bảo vệ dữ liệu](../superpowers/specs/2026-10-27-core-backend-design.md#9-hợp-đồng-ai-evidence-và-bảo-vệ-dữ-liệu)

```mermaid
sequenceDiagram
    autonumber
    participant Worker as AI Worker (Pipeline)
    participant DB as PostgreSQL (app / knowledge / audit)
    participant Resolver as PII Resolver Process
    participant Vault as PostgreSQL (vault)
    participant ML as Internal ML Service
    participant Redis as Redis Cache
    participant WS as WebSocket Gateway

    Worker->>DB: Claim job (stage=pipeline) bằng row lock<br/>Cấp lease_token, lease_until, status=running (TX ngắn)
    Worker->>Worker: Kiểm tra checksum artifacts theo release_manifest đã ghim

    Note over Worker,Vault: 1. Quét PII và Tokenize theo phạm vi Run
    Worker->>Resolver: RPC sanitize(run_id, context_ref)
    Resolver->>DB: Đọc raw message & business identifiers (kiểm tra ownership)
    Resolver->>Vault: INSERT vault.token_mappings (run_id, random_token, encrypted_value)
    Resolver-->>Worker: Trả về sanitized_text & privacy warnings

    alt Không xác định được an toàn PII (privacy_check_failed)
        Worker->>DB: TX: UPDATE run (status=escalated, reason=privacy_check_failed)<br/>UPDATE ticket (manual_required=true) + INSERT audit.events
        Worker--)WS: Notify run.changed
    else Sanitize thành công
        Note over Worker,ML: 2. Phân loại Intent (46 nhãn ML vs 12 intent sản phẩm)
        Worker->>ML: Predict {text: sanitized_text, expected_model_version}
        ML-->>Worker: {intent, confidence, model_version}
        Worker->>Worker: Kiểm tra contract 46 nhãn, ngưỡng confidence,<br/>ambiguity rules, 12 supported intents & sensitive gate

        Note over Worker,Redis: 3. Truy xuất Evidence (Knowledge + Commerce Snapshot)
        Worker->>Redis: Kiểm tra cache knowledge (HMAC key + KB/index version)
        Worker->>DB: Hybrid search knowledge (lọc quyền & hiệu lực trước top-3)<br/>+ đọc commerce snapshot mới (đã kiểm ownership & che PII)
        Worker->>Worker: Kiểm tra missing / expired / conflicting evidence

        alt Bất kỳ Safety Gate / Policy nào thất bại hoặc lỗi ML/Retrieval
            Worker->>DB: BEGIN TRANSACTION (Đối chiếu lease_token & context_version)
            DB->>DB: UPDATE pipeline_runs (status=escalated, reason_codes)
            DB->>DB: UPDATE tickets (manual_required=true, chuyển queue manager nếu nhạy cảm)
            DB->>DB: INSERT evidence_snapshots (nếu có) & INSERT audit.events
            Worker->>DB: COMMIT
            Worker--)WS: Notify run.changed & ticket.changed
        else Đạt tất cả Gate (Chuẩn bị gọi LLM)
            Worker->>Worker: Tạo prompt từ versioned template + sanitized_text + evidence<br/>Chạy PII scanner lần cuối trên outbound payload
            Worker->>DB: BEGIN TRANSACTION (Đối chiếu lease_token & run chưa superseded)
            DB->>DB: INSERT evidence_snapshots (bất biến)
            DB->>DB: INSERT jobs (stage=llm_egress, sanitized payload, deadline_at)
            DB->>DB: Hoàn tất job stage=pipeline & INSERT audit.events
            Worker->>DB: COMMIT (Nhả worker slot của stage pipeline)
        end
    end
```
