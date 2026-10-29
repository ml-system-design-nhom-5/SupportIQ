# SupportIQ Core Backend — Kế hoạch triển khai & Phân công 4 thành viên (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triển khai hoàn chỉnh Core Backend cho hệ thống SupportIQ theo kiến trúc Modular Monolith (2 API replica + AI Worker + PII Resolver process), đảm bảo luồng duyệt thủ công (Manual Fallback) hoạt động độc lập với AI, pipeline AI bất đồng bộ có kiểm soát PII/grounding, và phân công độc lập cho 4 thành viên nhóm.

**Architecture:** Modular monolith đặt tại `apps/core-backend` gồm 13 module nghiệp vụ chia sẻ một PostgreSQL instance (4 schema tách quyền: `app`, `knowledge`, `audit`, `vault`) và một Redis instance (cache + distributed rate limit). Worker AI và PII Resolver chạy ở process riêng từ cùng codebase; mọi quyết định kiểm duyệt (`review_decisions`), bản nháp (`drafts`), bằng chứng (`evidence_snapshots`) và nhật ký (`audit.events`) đều bất biến; không có bất kỳ luồng tự động gửi câu trả lời hay tự thực hiện giao dịch thương mại nào từ AI.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (`asyncpg`), PyJWT, `pwdlib[argon2]`, `cryptography` (AES-256-GCM), `redis.asyncio`, `httpx`, `pytest` + `pytest-asyncio`.

**Spec:**
- [Đặc tả thiết kế Core Backend](../specs/2026-10-27-core-backend-design.md)
- [Hợp đồng OpenAPI v1](../../api/core-backend.openapi.yaml)
- [Kiến trúc & Yêu cầu FR/NFR](../../ARCHITECTURE.md)
- [Sequence Diagrams](../../sequence-diagrams/README.md)

## Global Constraints

- Giữ đúng 13 module trong `apps/core-backend/src/modules`; không tách microservice cho từng module nghiệp vụ.
- Toàn bộ đường dẫn API dưới `/api/v1`, JSON `snake_case`, tên trường/enum/thông báo lỗi dùng tiếng Anh theo `docs/api/core-backend.openapi.yaml`; mọi lỗi trả `application/problem+json` (RFC 9457) với `type: "urn:supportiq:problem:<code>"`, `request_id`, không lộ stack trace hay raw PII.
- Mô hình ML đánh giá trên 46 nhãn Bitext; sản phẩm chỉ hỗ trợ đúng 12 intent: `track_order`, `cancel_order`, `delivery_time`, `delivery_issue`, `shipping_costs`, `return_policy`, `return_product`, `refund_policy`, `request_refund`, `refund_status`, `payment_issue`, `human_agent`. Mọi nhãn ngoài 12 intent chuyển `unsupported_intent`.
- `POST /tickets/{ticket_id}/decisions` với `approve` hoặc `edit` chỉ lưu nội dung đã duyệt và cập nhật `ticket.current_decision_id`; tuyệt đối không gửi câu trả lời cho khách hàng. Chỉ `POST /tickets/{ticket_id}/replies` do staff có quyền gọi mới công bố reply.
- Mọi mutation nghiệp vụ (`tickets`, `messages`, `runs`, `decisions`, `replies`, `orders`, `users`, `releases`) phải ghi `audit.events` trong cùng một DB transaction; runtime role của `audit` chỉ có quyền `INSERT` (và `SELECT` cho reader), không có `UPDATE/DELETE/TRUNCATE`. Thiếu audit thì rollback toàn bộ transaction.
- Chỉ process `resolver` mới có DB credential đọc/ghi schema `vault`. `core-api` và `ai-worker` không có quyền truy cập `vault.token_mappings`. Không để lọt PII thô (tên, địa chỉ, SĐT, email, mã đơn hàng) vào ML, retrieval ngoài miền tin cậy, LLM, queue, Redis, audit hay log.
- Các endpoint `POST /tickets`, `/messages`, `/runs`, `/decisions`, `/replies`, `/orders` bắt buộc header `Idempotency-Key` (TTL 24 giờ, fingerprint HMAC-SHA256 trên canonical body, kiểm tra sau RBAC và trước `If-Match`). Các mutation trên ticket bắt buộc `If-Match: "<ticket.version>"` (thiếu trả `428 precondition_required`, lệch trả `412 version_conflict`).
- Ngân sách thời gian toàn bộ AI run là 12 giây tính từ lúc nhận request tạo run (gồm cả queue wait); timeout mỗi lần gọi LLM là `min(8s, remaining_budget)` và không vượt 10 giây; retry tối đa 2 lần chỉ khi lỗi tạm thời, còn ngân sách và chắc chắn request chưa phát sinh xử lý hoặc có idempotency.
- Mục tiêu hiệu năng: p50 ≤ 4 giây, p95 ≤ 12 giây, hỗ trợ ≥ 5 phiên đồng thời với lỗi ≤ 1%, tổng RAM toàn stack demo ≤ ~5 GB trên máy 8 GB.

## Review Focus

Năm tình huống lỗi dễ lọt nhất khi chỉ kiểm thử happy-path, bắt buộc có test tự động gắn vào từng Task sở hữu:

1. **Gửi lại Approval cũ đã bị vô hiệu hóa (`stale approval replay`):** Khi staff đã `approve` decision $D_1$, nhưng sau đó có quyết định `reject`/`edit`/`escalate` mới, tạo run mới, đổi assignee/queue, hoặc khách gửi thêm message làm xóa/đổi `ticket.current_decision_id`, gọi `POST /tickets/{id}/replies` với $D_1$ phải trả `409 state_conflict` và không tạo bản ghi `app.replies` (Gắn vào **Task 5** và **Task 10**).
2. **Worker chết hoặc timeout sau khi đã gửi request sang LLM (`outcome_unknown`):** Khi `app.llm_attempts.state == "in_flight"` mà worker crash hoặc mất kết nối không xác định được provider đã xử lý hay chưa, trình phục hồi không được retry mù làm nhân đôi chi phí và không được ghi `cost = 0`; phải đánh dấu attempt `outcome_unknown`, chuyển run sang `escalated` (`reason_codes=["llm_unavailable"]`, `cost_status="unknown"`) (Gắn vào **Task 4** và **Task 9**).
3. **Thu hồi quyền hoặc đăng xuất khi Redis cache / WebSocket còn nóng:** Khi Admin hạ quyền/khóa tài khoản (`PATCH /users/{id}`) hoặc user logout (`DELETE /sessions/current`), mọi mutation nhạy cảm và WebSocket subscription phải kiểm tra `role_version`/session trực tiếp từ DB (hoặc bị chặn tức thì) thay vì chờ hết TTL 30 giây của Redis (Gắn vào **Task 1** và **Task 10**).
4. **Tài liệu Knowledge hết hạn trên Cache Hit hoặc đơn hàng đổi version trước khi gửi Reply:** Khi Redis trả về kết quả retrieval cache hit nhưng `valid_to <= now()`, hoặc khi đơn hàng tăng `version` giữa lúc tạo draft và lúc gọi `POST /replies`, hệ thống phải gắn cờ `expired_evidence` hoặc trả `409 evidence_changed` lúc duyệt/gửi (Gắn vào **Task 8** và **Task 5**).
5. **Sập PII Resolver / Vault hoặc AI Services trong lúc nhân viên xử lý thủ công (`manual fallback availability`):** Khi `resolver`, `ml-inference`, `redis` hoặc `egress-proxy` ngừng hoạt động, `GET /health/ready` vẫn trả `200 OK` (`ai_available=false`), và nhân viên vẫn đăng nhập, đọc ticket, tạo `ManualApproval` (`source="manual"`) và gửi `POST /replies` thành công nhờ bộ quét placeholder/PII cục bộ không phụ thuộc `vault` (Gắn vào **Task 5** và **Task 6**).

---

## Phân công 4 thành viên & Lộ trình Mốc bàn giao (M0 – M3)

| Thành viên | MSSV | Phụ trách chính | Task sở hữu (Owner) | Review chính cho |
| --- | --- | --- | --- | --- |
| **Đoàn Anh Minh** | 24021565 | Foundation, DB roles, Auth/RBAC, Privacy/Resolver/Vault, Docker Compose & Security | Task 0 (CORE-00), Task 1 (CORE-01), Task 6 (CORE-06), Task 11 (CORE-11) | Task 2, Task 4, Task 7 |
| **An Đức Minh Trí** | 24021645 | Tickets, Messages, Commerce Demo, Review Decisions, Explicit Reply, WebSocket & E2E | Task 2 (CORE-02), Task 5 (CORE-05), Task 10 (CORE-10) | Task 1, Task 3, Task 12 |
| **Nguyễn Công Phúc** | 24021598 | Orchestration State Machine, Durable Jobs/Leases, Intent ML Client, Escalation, Releases & Load Test | Task 4 (CORE-04), Task 7 (CORE-07), Task 12 (CORE-12) | Task 6, Task 8, Task 9 |
| **Phạm Gia Bách** | 24021382 | Immutable Audit, Reports, Hybrid Retrieval, Evidence Snapshots, LLM Prompt/Egress Proxy & Grounding | Task 3 (CORE-03), Task 8 (CORE-08), Task 9 (CORE-09) | Task 0, Task 5, Task 10, Task 11 |

```mermaid
flowchart TD
    T0["Task 0 (CORE-00): Bootstrap & Common Contracts — Minh"] --> T1["Task 1 (CORE-01): Auth & RBAC — Minh"]
    T0 --> T2["Task 2 (CORE-02): Tickets & Commerce — Trí"]
    T0 --> T3["Task 3 (CORE-03): Audit & Reports — Bách"]
    T0 --> T4["Task 4 (CORE-04): Jobs & Run State Machine — Phúc"]
    T1 --> T5["Task 5 (CORE-05): Review, Manual & Send Reply — Trí"]
    T2 --> T5
    T3 --> T5
    T1 --> T6["Task 6 (CORE-06): Privacy Scanner & Vault Resolver — Minh"]
    T2 --> T6
    T3 --> T6
    T4 --> T7["Task 7 (CORE-07): ML Intent, Escalation & Releases — Phúc"]
    T6 --> T7
    T2 --> T8["Task 8 (CORE-08): Hybrid Retrieval & Evidence — Bách"]
    T3 --> T8
    T6 --> T8
    T4 --> T9["Task 9 (CORE-09): LLM Draft & Egress Proxy — Bách"]
    T6 --> T9
    T7 --> T9
    T8 --> T9
    T4 --> T10["Task 10 (CORE-10): REST Recovery, WS & E2E — Trí"]
    T5 --> T10
    T5 --> T11["Task 11 (CORE-11): Multi-Replica Stack & Security — Minh"]
    T6 --> T11
    T7 --> T11
    T9 --> T11
    T10 --> T12["Task 12 (CORE-12): Full AI Pipeline & Load Verification — Phúc"]
    T11 --> T12
```

- **M0 (Foundation):** Hoàn thành **Task 0**. Cả 4 thành viên chạy được `pytest` trên DB PostgreSQL 4-schema và dùng chung các DTO/Interface nội bộ.
- **M1 (Manual Workflow Complete):** Hoàn thành **Task 1, Task 2, Task 3, Task 5**. Khách tạo ticket/order, nhân viên duyệt manual và gửi reply, audit ghi nguyên tử khi tắt toàn bộ AI.
- **M2 (Controlled AI Pipeline):** Hoàn thành **Task 4, Task 6, Task 7, Task 8, Task 9**. Worker chạy pipeline tạo draft có trích dẫn hoặc fallback có lý do, đảm bảo 0 PII lọt ra ngoài và 0 tự động gửi reply.
- **M3 (Production-Readiness Demo & Verification):** Hoàn thành **Task 10, Task 11, Task 12**. Chạy 2 replica Core API + Worker + Resolver + Proxy, vượt qua bộ test RBAC/PII/Resilience/Performance.

---

### Task 0 (CORE-00): Khởi tạo App Shell, Database Schemas/Roles, Problem Details & Hợp đồng Nội bộ

**Owner:** Đoàn Anh Minh | **Reviewer:** Phạm Gia Bách | **Milestone:** M0

**Files:**
- Create: `apps/core-backend/pyproject.toml`
- Create: `apps/core-backend/src/config.py`
- Create: `apps/core-backend/src/db.py`
- Create: `apps/core-backend/src/errors.py`
- Create: `apps/core-backend/src/contracts.py`
- Create: `apps/core-backend/src/idempotency.py`
- Create: `apps/core-backend/src/main.py`
- Create: `db/migrations/app/000_init_schemas_and_roles.sql`
- Create: `db/migrations/app/001_idempotency_records.sql`
- Create: `infra/compose/docker-compose.dev.yml`
- Test: `tests/integration/test_bootstrap_health_and_errors.py`

**Interfaces:**
- Consumes: Biến môi trường (`APP_DB_URL`, `AUDIT_WRITER_DB_URL`, `AUDIT_READER_DB_URL`, `VAULT_DB_URL`, `REDIS_URL`, `APP_ENCRYPTION_KEY`, `INTERNAL_SERVICE_TOKEN`).
- Produces:
  - `apps/core-backend/src/contracts.py`:
    - `Role = Literal["customer", "agent", "manager", "admin"]`
    - `AccessScope(actor_id: UUID, role: Role, role_version: int, session_id: UUID)`
    - `AuditEventInput(event_type: str, request_id: UUID, ticket_id: UUID | None, run_id: UUID | None, actor_id: UUID | None, details: dict[str, Any])`
    - `TicketContextRef(ticket_id: UUID, customer_id: UUID, order_id: UUID | None, context_version: int, version: int, handling_queue: Literal["standard", "manager"], status: Literal["open", "resolved", "closed"])`
  - `apps/core-backend/src/errors.py`:
    - `AppError(status: int, code: str, title: str, detail: str | None = None, errors: list[dict[str, str]] | None = None, headers: dict[str, str] | None = None)`
    - Format chuẩn RFC 9457 `application/problem+json` với `type = f"urn:supportiq:problem:{code}"` và header `X-Request-ID`.
  - `apps/core-backend/src/idempotency.py`:
    - `check_or_store_idempotency(session: AsyncSession, actor_id: UUID, method: str, route: str, key: str, canonical_body: bytes) -> IdempotencyRecord | None`
    - `parse_if_match(if_match_header: str | None, current_version: int) -> None` (ném `428 precondition_required` nếu thiếu, `412 version_conflict` nếu khác `f'"{current_version}"'`).

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_bootstrap_health_and_errors.py`:
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_live_and_ready_require_internal_token(client: AsyncClient):
    res_unauth = await client.get("/api/v1/health/live")
    assert res_unauth.status_code == 401
    assert res_unauth.headers["content-type"].startswith("application/problem+json")
    body = res_unauth.json()
    assert body["type"] == "urn:supportiq:problem:unauthenticated"
    assert "request_id" in body

    headers = {"Authorization": "Bearer test-internal-service-token"}
    res_live = await client.get("/api/v1/health/live", headers=headers)
    assert res_live.status_code == 200
    assert res_live.json() == {"data": {"status": "ok", "ai_available": False}}

    res_ready = await client.get("/api/v1/health/ready", headers=headers)
    assert res_ready.status_code == 200
    assert res_ready.json()["data"]["status"] == "ok"

@pytest.mark.asyncio
async def test_if_match_and_idempotency_conflict_contracts():
    from src.idempotency import parse_if_match
    from src.errors import AppError

    with pytest.raises(AppError) as exc_missing:
        parse_if_match(None, current_version=3)
    assert exc_missing.value.status == 428
    assert exc_missing.value.code == "precondition_required"

    with pytest.raises(AppError) as exc_mismatch:
        parse_if_match('"2"', current_version=3)
    assert exc_mismatch.value.status == 412
    assert exc_mismatch.value.code == "version_conflict"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_bootstrap_health_and_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src'`

- [ ] **Step 3: Implement schemas, roles, app bootstrap, RFC 9457 handler, and idempotency helpers**

1. Create `db/migrations/app/000_init_schemas_and_roles.sql` defining schemas `app`, `knowledge`, `audit`, `vault` and PostgreSQL roles `core_app_role`, `audit_writer_role`, `audit_reader_role`, `vault_resolver_role` where `core_app_role` has zero privileges on `vault`, and `audit_writer_role` has only `INSERT` on `audit`.
2. Create `db/migrations/app/001_idempotency_records.sql` with table `app.idempotency_records (id UUID PRIMARY KEY, actor_id UUID NOT NULL, method TEXT NOT NULL, route TEXT NOT NULL, key TEXT NOT NULL, request_hmac TEXT NOT NULL, resource_id UUID, response_status INT, response_body JSONB, response_headers JSONB, expires_at TIMESTAMPTZ NOT NULL, UNIQUE (actor_id, method, route, key))`.
3. Implement `apps/core-backend/src/config.py`, `src/db.py`, `src/contracts.py`, `src/errors.py`, `src/idempotency.py`, and `src/main.py` with `/api/v1/health/live` and `/api/v1/health/ready` plus middleware enforcing 64 KiB max JSON body (`413 payload_too_large`) and `X-Request-ID`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_bootstrap_health_and_errors.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core-backend db/migrations/app/000_init_schemas_and_roles.sql db/migrations/app/001_idempotency_records.sql infra/compose/docker-compose.dev.yml tests/integration/test_bootstrap_health_and_errors.py
git commit -m "feat(core): bootstrap FastAPI app, DB schemas/roles, RFC 9457 errors, and idempotency"
```

---

### Task 1 (CORE-01): Xác thực (Authentication), Quản lý Session, CSRF & Phân quyền RBAC

**Owner:** Đoàn Anh Minh | **Reviewer:** An Đức Minh Trí | **Milestone:** M1

**Files:**
- Create: `db/migrations/app/002_users_and_sessions.sql`
- Create: `apps/core-backend/src/modules/auth/models.py`
- Create: `apps/core-backend/src/modules/auth/schemas.py`
- Create: `apps/core-backend/src/modules/auth/service.py`
- Create: `apps/core-backend/src/modules/auth/routes.py`
- Modify: `apps/core-backend/src/main.py`
- Test: `tests/security/test_auth_and_rbac.py`

**Interfaces:**
- Consumes: `src.db.get_session`, `src.contracts.AccessScope`, `src.errors.AppError`, Redis client.
- Produces:
  - `auth.service.authenticate_request(session: AsyncSession, redis: Redis, token: str, require_fresh_db: bool = False) -> AccessScope`
  - `auth.service.authorize(scope: AccessScope, allowed_roles: set[Role]) -> None`
  - `auth.service.invalidate_user_sessions(session: AsyncSession, redis: Redis, user_id: UUID) -> None`
  - REST Endpoints: `POST /api/v1/sessions`, `POST /api/v1/sessions/refresh`, `DELETE /api/v1/sessions/current`, `GET /api/v1/me`, `GET /api/v1/users`, `PATCH /api/v1/users/{user_id}`.

- [ ] **Step 1: Write the failing test**

Create `tests/security/test_auth_and_rbac.py` covering login, cookie attributes (`HttpOnly; Secure; SameSite=Strict`), CSRF validation on refresh/logout, protection of the last active Admin, and **Review Focus #3** (`test_revoked_role_blocks_mutation_with_warm_cache`):
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_refresh_csrf_and_last_admin_protection(client: AsyncClient):
    res = await client.post(
        "/api/v1/sessions",
        json={"email": "admin@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 900
    assert data["user"]["role"] == "admin"
    assert "refresh_token=" in res.headers.get("set-cookie", "")

    admin_token = data["access_token"]
    admin_id = data["user"]["id"]
    # Cannot demote or deactivate the sole active Admin
    demote = await client.patch(
        f"/api/v1/users/{admin_id}",
        json={"role": "agent"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert demote.status_code == 409
    assert demote.json()["code"] == "state_conflict"

@pytest.mark.asyncio
async def test_revoked_role_blocks_mutation_with_warm_cache(client: AsyncClient):
    # Agent logs in and warms cache via GET /me
    agent_login = await client.post(
        "/api/v1/sessions",
        json={"email": "agent1@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    agent_token = agent_login.json()["data"]["access_token"]
    agent_id = agent_login.json()["data"]["user"]["id"]
    assert (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {agent_token}"})).status_code == 200

    # Admin deactivates agent while cache is still within 30s TTL
    admin_login = await client.post(
        "/api/v1/sessions",
        json={"email": "admin@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    admin_token = admin_login.json()["data"]["access_token"]
    patch_res = await client.patch(
        f"/api/v1/users/{agent_id}",
        json={"active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert patch_res.status_code == 200

    # Agent's existing JWT is immediately rejected
    me_after = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {agent_token}"})
    assert me_after.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/security/test_auth_and_rbac.py -v`
Expected: FAIL with `404 Not Found` on `/api/v1/sessions`

- [ ] **Step 3: Implement users/sessions migration, Argon2 + JWT auth service, and RBAC routes**

1. Create `db/migrations/app/002_users_and_sessions.sql` with `app.users (id, email UNIQUE, password_hash, role, active, role_version, created_at)` and `app.sessions (id, user_id, refresh_token_hash, csrf_token_hash, expires_at, revoked_at, created_at)` plus seeded demo accounts for `customer`, `agent`, `manager`, `admin`.
2. Implement `apps/core-backend/src/modules/auth/service.py` using `pwdlib` (Argon2) and `PyJWT` (15-minute access token with `sub`, `sid`, `rv`; 8-hour rotating refresh cookie; Redis permission cache with 30s TTL; mandatory DB session/`role_version` check when `require_fresh_db=True` and active cache eviction on logout/role update).
3. Implement `apps/core-backend/src/modules/auth/routes.py` and mount under `/api/v1`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/security/test_auth_and_rbac.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add db/migrations/app/002_users_and_sessions.sql apps/core-backend/src/modules/auth apps/core-backend/src/main.py tests/security/test_auth_and_rbac.py
git commit -m "feat(auth): implement session lifecycle, CSRF validation, and DB-backed RBAC"
```

---

### Task 2 (CORE-02): Quản lý Ticket, Hội thoại (Messages) & Nghiệp vụ Commerce Demo

**Owner:** An Đức Minh Trí | **Reviewer:** Đoàn Anh Minh | **Milestone:** M1

**Files:**
- Create: `db/migrations/app/003_commerce_and_tickets.sql`
- Create: `data/business/demo_seed.json`
- Create: `apps/core-backend/src/crypto.py`
- Create: `apps/core-backend/src/modules/commerce/models.py`
- Create: `apps/core-backend/src/modules/commerce/schemas.py`
- Create: `apps/core-backend/src/modules/commerce/service.py`
- Create: `apps/core-backend/src/modules/commerce/routes.py`
- Create: `apps/core-backend/src/modules/tickets/models.py`
- Create: `apps/core-backend/src/modules/tickets/schemas.py`
- Create: `apps/core-backend/src/modules/tickets/service.py`
- Create: `apps/core-backend/src/modules/tickets/routes.py`
- Test: `tests/integration/test_tickets_and_commerce.py`

**Interfaces:**
- Consumes: `auth.service.authenticate_request`, `src.idempotency`, `audit.service.append_event` (protocol hook).
- Produces:
  - `src.crypto.encrypt_text(plaintext: str) -> bytes` & `decrypt_text(ciphertext: bytes) -> str` (AES-256-GCM).
  - `tickets.service.get_ticket_for_actor(session: AsyncSession, ticket_id: UUID, scope: AccessScope, for_update: bool = False) -> TicketModel` (kiểm tra ownership cho `customer`, queue/assignment cho `agent`, toàn quyền cho `manager`, chặn `admin` trả `403`).
  - `tickets.service.clear_current_decision_and_bump_version(session: AsyncSession, ticket: TicketModel, bump_context: bool = False) -> None`
  - `commerce.service.get_order_snapshot_for_ticket(session: AsyncSession, ticket_id: UUID, scope: AccessScope) -> OrderSnapshotDTO | None`
  - REST Endpoints: `GET /products`, `POST /orders`, `GET /orders`, `GET /orders/{order_id}`, `GET /tickets`, `POST /tickets`, `GET /tickets/{ticket_id}`, `PATCH /tickets/{ticket_id}`, `GET /tickets/{ticket_id}/messages`, `POST /tickets/{ticket_id}/messages`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_tickets_and_commerce.py`:
```python
import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_customer_checkout_ticket_creation_and_scope_isolation(
    client: AsyncClient, customer_token: str, other_customer_token: str, agent_token: str, admin_token: str
):
    products = (await client.get("/api/v1/products")).json()["data"]
    prod_id = products[0]["id"]

    # Customer creates demo order (server calculates total_minor)
    order_res = await client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": prod_id, "quantity": 2}]},
        headers={"Authorization": f"Bearer {customer_token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert order_res.status_code == 201
    order = order_res.json()["data"]
    assert order["demo"] is True
    assert order["total_minor"] == products[0]["unit_price_minor"] * 2

    # Other customer cannot attach this order_id or view it
    bad_ticket = await client.post(
        "/api/v1/tickets",
        json={"message": "Where is my order?", "order_id": order["id"]},
        headers={"Authorization": f"Bearer {other_customer_token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert bad_ticket.status_code == 404

    # Owner customer creates ticket
    t_res = await client.post(
        "/api/v1/tickets",
        json={"message": "Where is my order?", "order_id": order["id"]},
        headers={"Authorization": f"Bearer {customer_token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert t_res.status_code == 201
    assert t_res.headers["ETag"] == '"1"'
    ticket_data = t_res.json()["data"]
    assert "current_run_id" not in ticket_data
    assert "current_decision_id" not in ticket_data

    # Admin is forbidden from reading ticket content
    admin_get = await client.get(
        f"/api/v1/tickets/{ticket_data['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_get.status_code == 403

    # Agent claims unassigned standard ticket and sees staff pointers
    claim_res = await client.patch(
        f"/api/v1/tickets/{ticket_data['id']}",
        json={"status": "open"},
        headers={"Authorization": f"Bearer {agent_token}", "If-Match": '"1"'},
    )
    assert claim_res.status_code == 200
    assert "current_run_id" in claim_res.json()["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_tickets_and_commerce.py -v`
Expected: FAIL with `404 Not Found` on `/api/v1/products`

- [ ] **Step 3: Implement commerce & tickets migrations, AES-GCM encryption, and scoped endpoints**

1. Create `db/migrations/app/003_commerce_and_tickets.sql` defining `app.products`, `app.orders`, `app.order_items`, `app.shipments`, `app.refunds`, `app.tickets`, `app.messages` with composite indexes `tickets(customer_id, created_at DESC, id DESC)`, `tickets(handling_queue, status, updated_at DESC, id DESC)`, `messages(ticket_id, created_at, id)`.
2. Implement `apps/core-backend/src/crypto.py` for AES-256-GCM encryption of `app.messages.content_ciphertext`.
3. Implement `commerce` and `tickets` services/routes enforcing: Customer DTO omits `current_run_id` and `current_decision_id`; Staff DTO includes them; new customer message on `resolved` ticket reopens to `open`, increments `context_version` and `version`, clears `current_decision_id`; `closed` ticket rejects new messages with `409 state_conflict`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_tickets_and_commerce.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db/migrations/app/003_commerce_and_tickets.sql data/business/demo_seed.json apps/core-backend/src/crypto.py apps/core-backend/src/modules/commerce apps/core-backend/src/modules/tickets tests/integration/test_tickets_and_commerce.py
git commit -m "feat(tickets,commerce): implement scoped tickets, encrypted messages, and demo commerce"
```

---

### Task 3 (CORE-03): Nhật ký Kiểm toán Bất biến (Immutable Audit) & Báo cáo Quản lý (Reports)

**Owner:** Phạm Gia Bách | **Reviewer:** An Đức Minh Trí | **Milestone:** M1

**Files:**
- Create: `db/migrations/audit/001_audit_events.sql`
- Create: `apps/core-backend/src/modules/audit/models.py`
- Create: `apps/core-backend/src/modules/audit/schemas.py`
- Create: `apps/core-backend/src/modules/audit/service.py`
- Create: `apps/core-backend/src/modules/audit/routes.py`
- Create: `apps/core-backend/src/modules/reports/schemas.py`
- Create: `apps/core-backend/src/modules/reports/service.py`
- Create: `apps/core-backend/src/modules/reports/routes.py`
- Test: `tests/integration/test_audit_and_reports.py`

**Interfaces:**
- Consumes: `src.contracts.AuditEventInput`, `src.contracts.AccessScope`, caller's active `AsyncSession`.
- Produces:
  - `audit.service.append_event(session: AsyncSession, event: AuditEventInput) -> UUID` (chạy trong cùng transaction của caller; tự động kiểm tra key allowlist và từ chối nếu `details` chứa chuỗi khớp pattern PII thô; nếu insert lỗi thì ném exception làm rollback caller transaction).
  - REST Endpoints: `GET /api/v1/tickets/{ticket_id}/events`, `GET /api/v1/reports/summary`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_audit_and_reports.py`:
```python
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_audit_is_insert_only_and_rollback_on_failure(db_session: AsyncSession):
    # Verify PostgreSQL trigger / permission rejects UPDATE and DELETE on audit.events
    with pytest.raises(Exception):
        await db_session.execute(text("DELETE FROM audit.events"))
    await db_session.rollback()

@pytest.mark.asyncio
async def test_reports_summary_excludes_manual_from_ai_acceptance_and_tracks_unknown_cost(
    client: AsyncClient, manager_token: str, seeded_report_fixtures
):
    res = await client.get(
        "/api/v1/reports/summary",
        params={"from": "2026-10-01T00:00:00Z", "to": "2026-10-30T00:00:00Z"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert res.status_code == 200
    report = res.json()["data"]
    # Manual approvals are not counted in ai_review_counts
    assert report["ai_review_counts"] == {"approved": 2, "edited": 1, "rejected": 1}
    assert report["reviewed_drafts"] == 4
    # Unknown cost runs are counted separately and never coerced to 0
    assert report["cost"]["unknown_runs"] == 1
    assert report["cost"]["known_total_micro"] == 3000
    assert report["cost"]["known_average_per_run_micro"] == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_audit_and_reports.py -v`
Expected: FAIL with `relation "audit.events" does not exist`

- [ ] **Step 3: Implement append-only `audit.events` schema, `append_event`, and `/reports/summary`**

1. Create `db/migrations/audit/001_audit_events.sql` with table `audit.events`, index `audit.events(ticket_id, occurred_at, id)`, and a database trigger + role privilege revocation blocking `UPDATE`, `DELETE`, and `TRUNCATE`.
2. Implement `apps/core-backend/src/modules/audit/service.py` and `routes.py` (`GET /tickets/{ticket_id}/events` scoped to assigned Agent or Manager).
3. Implement `apps/core-backend/src/modules/reports/service.py` and `routes.py` (`GET /reports/summary` for Manager only, max interval 31 days, 30s Redis cache, separating `ai_review_counts` from manual approvals, counting only the first terminal decision per draft, and reporting `unknown_runs` / `known_coverage` accurately).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_audit_and_reports.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db/migrations/audit/001_audit_events.sql apps/core-backend/src/modules/audit apps/core-backend/src/modules/reports tests/integration/test_audit_and_reports.py
git commit -m "feat(audit,reports): add immutable audit store and manager summary reports"
```

---

### Task 4 (CORE-04): Hàng đợi Job Bền vững (Durable Jobs), Lease Worker & State Machine của AI Run

**Owner:** Nguyễn Công Phúc | **Reviewer:** Đoàn Anh Minh | **Milestone:** M2

**Files:**
- Create: `db/migrations/app/004_releases_runs_jobs_and_attempts.sql`
- Create: `apps/core-backend/src/modules/orchestration/models.py`
- Create: `apps/core-backend/src/modules/orchestration/schemas.py`
- Create: `apps/core-backend/src/modules/orchestration/service.py`
- Create: `apps/core-backend/src/modules/orchestration/worker.py`
- Create: `apps/core-backend/src/modules/orchestration/routes.py`
- Test: `tests/integration/test_orchestration_jobs_and_leases.py`

**Interfaces:**
- Consumes: `tickets.service.get_ticket_for_actor`, `tickets.service.clear_current_decision_and_bump_version`, `audit.service.append_event`, Redis rate/concurrency limiter.
- Produces:
  - `orchestration.service.create_run(session: AsyncSession, redis: Redis, ticket_id: UUID, payload: RunCreate, scope: AccessScope, if_match: str, idempotency_key: str) -> RunAccepted`
  - `orchestration.service.supersede_active_runs(session: AsyncSession, ticket_id: UUID, reason: str) -> None`
  - `orchestration.worker.claim_next_job(session: AsyncSession, stage: Literal["pipeline", "llm_egress"], worker_id: str, lease_seconds: int = 5) -> ClaimedJob | None` (dùng `SELECT ... FOR UPDATE SKIP LOCKED`, cấp `lease_token` UUID mới).
  - `orchestration.worker.complete_pipeline_stage_and_enqueue_egress(session: AsyncSession, run_id: UUID, lease_token: UUID, sanitized_payload: dict[str, Any]) -> bool`
  - `orchestration.worker.recover_expired_runs_and_attempts(session: AsyncSession) -> int`
  - REST Endpoints: `POST /api/v1/tickets/{ticket_id}/runs`, `GET /api/v1/runs/{run_id}`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_orchestration_jobs_and_leases.py` including **Review Focus #2** (`test_recover_in_flight_llm_attempt_marks_outcome_unknown_without_retry`):
```python
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.orchestration.worker import (
    claim_next_job,
    commit_run_draft,
    recover_expired_runs_and_attempts,
)

@pytest.mark.asyncio
async def test_stale_lease_token_cannot_overwrite_superseded_run(db_session: AsyncSession, queued_run_fixture):
    run_id = queued_run_fixture.id
    claimed_1 = await claim_next_job(db_session, stage="pipeline", worker_id="w1", lease_seconds=0)
    assert claimed_1 is not None

    # Lease expires and worker 2 claims the job with a new lease_token
    claimed_2 = await claim_next_job(db_session, stage="pipeline", worker_id="w2", lease_seconds=10)
    assert claimed_2 is not None
    assert claimed_2.lease_token != claimed_1.lease_token

    # Worker 1 tries to commit late with old lease_token -> rejected
    committed = await commit_run_draft(
        db_session, run_id=run_id, lease_token=claimed_1.lease_token, draft_body="Late draft", citation_ids=["c1"]
    )
    assert committed is False

@pytest.mark.asyncio
async def test_recover_in_flight_llm_attempt_marks_outcome_unknown_without_retry(
    db_session: AsyncSession, in_flight_expired_egress_fixture
):
    run_id = in_flight_expired_egress_fixture.id
    recovered = await recover_expired_runs_and_attempts(db_session)
    assert recovered == 1

    run = await db_session.get(type(in_flight_expired_egress_fixture), run_id)
    assert run.status == "escalated"
    assert "llm_unavailable" in run.reason_codes
    assert run.cost_status == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_orchestration_jobs_and_leases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.orchestration'`

- [ ] **Step 3: Implement run/job/attempt tables, atomic run creation, lease locking, and crash recovery**

1. Create `db/migrations/app/004_releases_runs_jobs_and_attempts.sql` with `app.release_manifests`, `app.pipeline_runs`, `app.jobs (UNIQUE (run_id, stage))`, `app.llm_attempts (UNIQUE (run_id, attempt_no))`, `app.evidence_snapshots (UNIQUE (run_id, citation_id))`, `app.drafts (run_id UNIQUE)`.
2. Implement `orchestration/service.py` and `worker.py` enforcing the 12-second total deadline (`deadline_at = created_at + 12s`), superseding older active runs on new run creation, releasing the `pipeline` worker slot immediately after inserting the `llm_egress` job, and marking crashed `in_flight` LLM attempts as `outcome_unknown` without blind retry.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_orchestration_jobs_and_leases.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db/migrations/app/004_releases_runs_jobs_and_attempts.sql apps/core-backend/src/modules/orchestration tests/integration/test_orchestration_jobs_and_leases.py
git commit -m "feat(orchestration): implement durable job leases, run state machine, and crash recovery"
```

---

### Task 5 (CORE-05): Kiểm duyệt (Review Decisions), Duyệt Thủ công (Manual Fallback) & Chủ động Gửi Reply

**Owner:** An Đức Minh Trí | **Reviewer:** Phạm Gia Bách | **Milestone:** M1

**Files:**
- Create: `db/migrations/app/005_decisions_and_replies.sql`
- Create: `apps/core-backend/src/modules/review/models.py`
- Create: `apps/core-backend/src/modules/review/schemas.py`
- Create: `apps/core-backend/src/modules/review/service.py`
- Create: `apps/core-backend/src/modules/review/routes.py`
- Create: `apps/core-backend/src/modules/feedback/service.py`
- Test: `tests/integration/test_review_and_reply.py`

**Interfaces:**
- Consumes: `tickets.service.get_ticket_for_actor`, `audit.service.append_event`, `orchestration.service.supersede_active_runs`, `privacy.scanner.assert_no_unresolved_tokens_or_raw_pii_leak` (local regex/heuristic validator), `retrieval.validator.verify_evidence_still_valid`.
- Produces:
  - `review.service.record_decision(session: AsyncSession, ticket_id: UUID, payload: DecisionCreate, scope: AccessScope, if_match: str, idempotency_key: str) -> Decision`
  - `review.service.send_reply(session: AsyncSession, ticket_id: UUID, payload: ReplyCreate, scope: AccessScope, if_match: str, idempotency_key: str) -> Reply`
  - REST Endpoints: `GET /api/v1/tickets/{ticket_id}/decisions`, `POST /api/v1/tickets/{ticket_id}/decisions`, `POST /api/v1/tickets/{ticket_id}/replies`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_review_and_reply.py` covering **Review Focus #1** (`test_send_reply_rejects_stale_approval_after_reject_or_new_message`), **Review Focus #4** (`test_send_reply_fails_with_409_when_order_version_changes`), and **Review Focus #5** (`test_manual_approval_and_send_succeed_when_ai_and_resolver_down`):
```python
import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_send_reply_rejects_stale_approval_after_reject_or_new_message(
    client: AsyncClient, agent_token: str, assigned_ticket_with_draft
):
    t_id = assigned_ticket_with_draft["ticket_id"]
    draft_id = assigned_ticket_with_draft["draft_id"]

    # 1. Agent approves draft -> creates Decision D1, does NOT create a public reply
    d1_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={"source": "ai", "action": "approve", "draft_id": draft_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'},
    )
    assert d1_res.status_code == 201
    d1_id = d1_res.json()["data"]["id"]

    # 2. Agent subsequently rejects the same draft -> clears current_decision_id
    d2_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={"source": "ai", "action": "reject", "draft_id": draft_id, "reason": "Outdated policy"},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"3"'},
    )
    assert d2_res.status_code == 201

    # 3. Attempting to send D1 must fail with 409 state_conflict
    send_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": d1_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"4"'},
    )
    assert send_res.status_code == 409
    assert send_res.json()["code"] == "state_conflict"

@pytest.mark.asyncio
async def test_manual_approval_and_send_succeed_when_ai_and_resolver_down(
    client: AsyncClient, agent_token: str, customer_token: str, assigned_open_ticket, down_ai_and_resolver
):
    t_id = assigned_open_ticket["id"]
    dec_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={
            "source": "manual",
            "action": "approve",
            "body": "Your order is currently in transit and will arrive tomorrow.",
            "reason": "Verified directly from order table during AI outage",
        },
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'},
    )
    assert dec_res.status_code == 201
    dec_id = dec_res.json()["data"]["id"]

    reply_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": dec_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"3"'},
    )
    assert reply_res.status_code == 201

    # Customer now sees the outbound reply
    msgs = (await client.get(f"/api/v1/tickets/{t_id}/messages", headers={"Authorization": f"Bearer {customer_token}"})).json()["data"]
    assert any(m["direction"] == "outbound" and "in transit" in m["body"] for m in msgs)

@pytest.mark.asyncio
async def test_send_reply_fails_with_409_when_order_version_changes(
    client: AsyncClient, agent_token: str, approved_decision_with_order_snapshot, bump_order_version
):
    t_id = approved_decision_with_order_snapshot["ticket_id"]
    dec_id = approved_decision_with_order_snapshot["decision_id"]
    await bump_order_version(approved_decision_with_order_snapshot["order_id"])

    send_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": dec_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"3"'},
    )
    assert send_res.status_code == 409
    assert send_res.json()["code"] == "evidence_changed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_review_and_reply.py -v`
Expected: FAIL with `404 Not Found` on `/api/v1/tickets/{id}/decisions`

- [ ] **Step 3: Implement `review_decisions` & `replies` migrations, lock ordering (`ticket -> run -> decision`), and review/send endpoints**

1. Create `db/migrations/app/005_decisions_and_replies.sql` with immutable tables `app.review_decisions` and `app.replies (decision_id UUID UNIQUE NOT NULL)` plus FK pointers `tickets.current_run_id` and `tickets.current_decision_id`.
2. Implement `review/service.py` enforcing:
   - Lock acquisition order `ticket -> run -> decision` inside one transaction with `audit.service.append_event`.
   - `AiApproval` / `AiEdit` rejects unresolved token placeholders (`{{TOKEN_...}}` or `[PII_...]`) or mismatched `final_intent` with `409 state_conflict`.
   - Sensitivity gate runs on both `final_intent` and `body` for AI and manual decisions (Agent cannot approve sensitive actions like `cancel_order` or `request_refund` — requires Manager on `manager` queue).
   - `send_reply` verifies `ticket.current_decision_id == payload.decision_id`, `decision.action in ("approve", "edit")`, `context_version == ticket.context_version`, and re-verifies knowledge document validity + business order version (`409 evidence_changed` if changed), then inserts `app.replies`, sets `ticket.status = "resolved"`, and clears `ticket.current_decision_id`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_review_and_reply.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add db/migrations/app/005_decisions_and_replies.sql apps/core-backend/src/modules/review apps/core-backend/src/modules/feedback tests/integration/test_review_and_reply.py
git commit -m "feat(review): implement immutable decisions, manual fallback, and atomic reply delivery"
```

---

### Task 6 (CORE-06): Bộ quét PII (PII Scanner), Tiến trình Resolver & Bảo mật Token Vault

**Owner:** Đoàn Anh Minh | **Reviewer:** Nguyễn Công Phúc | **Milestone:** M2

**Files:**
- Create: `db/migrations/token-vault/001_token_mappings.sql`
- Create: `apps/core-backend/src/modules/privacy/scanner.py`
- Create: `apps/core-backend/src/modules/privacy/resolver_app.py`
- Create: `apps/core-backend/src/modules/privacy/client.py`
- Test: `tests/security/test_privacy_scanner_and_vault.py`

**Interfaces:**
- Consumes: `VAULT_DB_URL` (chỉ cấp cho `resolver_app.py`), `APP_DB_URL`, `INTERNAL_SERVICE_TOKEN`.
- Produces:
  - `privacy.scanner.scan_and_mask_text(text: str, run_id: UUID) -> ScanResult(sanitized_text: str, mappings: dict[str, str], uncertain_pii: bool, warnings: list[str])`
  - `privacy.scanner.contains_unresolved_placeholder(text: str) -> bool` (hàm thuần không cần kết nối `vault`, phục vụ **Task 5**).
  - `privacy.client.sanitize_for_run(run_id: UUID, ticket_id: UUID, scope: AccessScope) -> SanitizedRunContext` (gọi RPC nội bộ tới `resolver_app.py`).
  - `privacy.resolver_app`: Internal FastAPI process với 2 route nội bộ `POST /internal/v1/sanitize` và `POST /internal/v1/purge-expired`.

- [ ] **Step 1: Write the failing test**

Create `tests/security/test_privacy_scanner_and_vault.py` including **Review Focus #5** (`test_local_pii_scanner_rejects_unresolved_token_placeholders_without_vault`):
```python
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.privacy.scanner import scan_and_mask_text, contains_unresolved_placeholder

def test_local_pii_scanner_rejects_unresolved_token_placeholders_without_vault():
    run_id = uuid.uuid4()
    raw = "Hi, I am Alice Nguyen, phone +1-415-555-0199, email alice@example.com, order ORD-998877, living at 742 Evergreen Terrace."
    res = scan_and_mask_text(raw, run_id=run_id)
    assert "Alice Nguyen" not in res.sanitized_text
    assert "415-555-0199" not in res.sanitized_text
    assert "alice@example.com" not in res.sanitized_text
    assert "ORD-998877" not in res.sanitized_text
    assert "742 Evergreen Terrace" not in res.sanitized_text
    assert contains_unresolved_placeholder(res.sanitized_text) is True
    assert contains_unresolved_placeholder("Your order will arrive tomorrow.") is False

@pytest.mark.asyncio
async def test_core_app_role_cannot_access_vault_schema(db_session: AsyncSession):
    with pytest.raises(Exception):
        await db_session.execute(text("SELECT * FROM vault.token_mappings"))
    await db_session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/security/test_privacy_scanner_and_vault.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.privacy'`

- [ ] **Step 3: Implement `vault.token_mappings`, pure PII scanner, and isolated Resolver RPC process**

1. Create `db/migrations/token-vault/001_token_mappings.sql` with table `vault.token_mappings (id UUID PRIMARY KEY, run_id UUID NOT NULL, token TEXT NOT NULL, pii_type TEXT NOT NULL, encrypted_value BYTEA NOT NULL, expires_at TIMESTAMPTZ NOT NULL, UNIQUE (run_id, token))`, granting `SELECT, INSERT, DELETE` exclusively to `vault_resolver_role`.
2. Implement `apps/core-backend/src/modules/privacy/scanner.py` detecting names, addresses, phone numbers, emails, and order IDs, replacing them with run-scoped tokens `<PII:TYPE:RANDOM_HEX>` and flagging `uncertain_pii=True` when free-form name/address heuristics are ambiguous.
3. Implement `resolver_app.py` and `client.py` with 24-hour / ticket-close expiration purge.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/security/test_privacy_scanner_and_vault.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add db/migrations/token-vault/001_token_mappings.sql apps/core-backend/src/modules/privacy tests/security/test_privacy_scanner_and_vault.py
git commit -m "feat(privacy): add PII scanner, isolated vault resolver process, and role separation"
```

---

### Task 7 (CORE-07): ML Intent Client, Policy 46-Nhãn / 12-Intent, Escalation Routing & Release Manifests

**Owner:** Nguyễn Công Phúc | **Reviewer:** Đoàn Anh Minh | **Milestone:** M2

**Files:**
- Create: `apps/core-backend/config/policies/intent_policy.v1.json`
- Create: `apps/core-backend/src/modules/intent/schemas.py`
- Create: `apps/core-backend/src/modules/intent/client.py`
- Create: `apps/core-backend/src/modules/escalation/service.py`
- Create: `apps/core-backend/src/modules/orchestration/releases_routes.py`
- Create: `services/ml-inference/src/app.py`
- Test: `tests/unit/test_intent_policy_and_escalation.py`

**Interfaces:**
- Consumes: `apps/core-backend/config/policies/intent_policy.v1.json`, `ML_INFERENCE_URL`.
- Produces:
  - `intent.client.classify_intent(sanitized_text: str, expected_model_version: str, request_id: UUID, timeout_sec: float = 1.0) -> IntentPrediction`
  - `escalation.service.evaluate_intent_gates(prediction: IntentPrediction, intent_override: str | None, policy: IntentPolicy) -> GateDecision(allowed: bool, final_intent: str, target_queue: Literal["standard", "manager"], reason_codes: list[ReasonCode])`
  - REST Endpoints: `GET /api/v1/releases`, `PUT /api/v1/releases/current`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_intent_policy_and_escalation.py`:
```python
import math
import pytest
from src.modules.intent.schemas import IntentPrediction, IntentPolicy
from src.modules.escalation.service import evaluate_intent_gates, load_policy

def test_46_labels_contract_and_12_supported_intents():
    policy: IntentPolicy = load_policy("apps/core-backend/config/policies/intent_policy.v1.json")
    assert len(policy.all_46_labels) == 46
    assert len(policy.supported_12_intents) == 12

    # Out-of-scope Bitext label (e.g., 'create_account') -> unsupported_intent
    pred_oos = IntentPrediction(intent="create_account", confidence=0.96, model_version="v1.0.0")
    gate_oos = evaluate_intent_gates(pred_oos, intent_override=None, policy=policy)
    assert gate_oos.allowed is False
    assert "unsupported_intent" in gate_oos.reason_codes

    # Unknown label outside 46 labels -> invalid_model_output
    pred_bad = IntentPrediction(intent="invented_label", confidence=0.90, model_version="v1.0.0")
    gate_bad = evaluate_intent_gates(pred_bad, intent_override=None, policy=policy)
    assert gate_bad.allowed is False
    assert "invalid_model_output" in gate_bad.reason_codes

    # Sensitive action intent ('request_refund') -> routes to manager queue with sensitive_request
    pred_refund = IntentPrediction(intent="request_refund", confidence=0.94, model_version="v1.0.0")
    gate_refund = evaluate_intent_gates(pred_refund, intent_override=None, policy=policy)
    assert gate_refund.target_queue == "manager"
    assert "sensitive_request" in gate_refund.reason_codes

    # NaN confidence -> invalid_model_output
    pred_nan = IntentPrediction(intent="track_order", confidence=math.nan, model_version="v1.0.0")
    gate_nan = evaluate_intent_gates(pred_nan, intent_override=None, policy=policy)
    assert "invalid_model_output" in gate_nan.reason_codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_intent_policy_and_escalation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.intent'`

- [ ] **Step 3: Implement 46-label policy JSON, ML client, escalation evaluator, and release manifest endpoints**

1. Create `apps/core-backend/config/policies/intent_policy.v1.json` listing all 46 Bitext labels, the exact 12 supported intents, calibrated confidence thresholds, and sensitive action intents (`cancel_order`, `request_refund`, `return_product`, `payment_issue`, `human_agent`).
2. Implement `intent/client.py`, `escalation/service.py`, `services/ml-inference/src/app.py`, and admin release manifest endpoints (`GET /releases`, `PUT /releases/current` requiring `offline_gate == "passed"` and atomic `expected_current_release_id` check).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_intent_policy_and_escalation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/core-backend/config/policies/intent_policy.v1.json apps/core-backend/src/modules/intent apps/core-backend/src/modules/escalation apps/core-backend/src/modules/orchestration/releases_routes.py services/ml-inference tests/unit/test_intent_policy_and_escalation.py
git commit -m "feat(intent,escalation): enforce 46-label contract, 12-intent scope, and release manifests"
```

---

### Task 8 (CORE-08): Truy xuất Tri thức Lai (Hybrid Retrieval), Kiểm tra Mâu thuẫn/Hiệu lực & Evidence Snapshots

**Owner:** Phạm Gia Bách | **Reviewer:** Nguyễn Công Phúc | **Milestone:** M2

**Files:**
- Create: `db/migrations/knowledge/001_knowledge_documents.sql`
- Create: `data/knowledge/approved_kb.v1.json`
- Create: `apps/core-backend/src/modules/retrieval/models.py`
- Create: `apps/core-backend/src/modules/retrieval/schemas.py`
- Create: `apps/core-backend/src/modules/retrieval/service.py`
- Create: `apps/core-backend/src/modules/retrieval/validator.py`
- Test: `tests/evaluation/test_retrieval_and_evidence_validity.py`

**Interfaces:**
- Consumes: `commerce.service.get_order_snapshot_for_ticket`, Redis cache (`retrieval` namespace, TTL 60s), `knowledge.document_versions`.
- Produces:
  - `retrieval.service.retrieve_evidence(session: AsyncSession, redis: Redis, run_id: UUID, sanitized_query: str, final_intent: str, scope: AccessScope, release: ReleaseManifest, now: datetime) -> RetrievalResult(evidence: list[Evidence], reason_codes: list[ReasonCode])`
  - `retrieval.validator.verify_evidence_still_valid(session: AsyncSession, run_id: UUID, now: datetime) -> bool` (gọi lại ở bước `approve` và `send_reply` của **Task 5**).

- [ ] **Step 1: Write the failing test**

Create `tests/evaluation/test_retrieval_and_evidence_validity.py` including **Review Focus #4** (`test_retrieval_cache_hit_rechecks_document_validity_and_scope`):
```python
from datetime import datetime, timedelta, timezone
import pytest
from src.modules.retrieval.service import retrieve_evidence

@pytest.mark.asyncio
async def test_retrieval_cache_hit_rechecks_document_validity_and_scope(
    db_session, redis_client, seeded_kb_with_short_expiry, agent_scope, active_release
):
    t0 = datetime(2026, 10, 29, 9, 0, 0, tzinfo=timezone.utc)
    # First call populates 60s Redis cache while document is valid (valid_to = t0 + 20s)
    res1 = await retrieve_evidence(
        db_session, redis_client, run_id=seeded_kb_with_short_expiry.run1_id,
        sanitized_query="What is the return window?", final_intent="return_policy",
        scope=agent_scope, release=active_release, now=t0
    )
    assert res1.reason_codes == []
    assert len(res1.evidence) >= 1

    # Second call 30s later hits the 60s Redis cache, but document valid_to has now passed!
    t1 = t0 + timedelta(seconds=30)
    res2 = await retrieve_evidence(
        db_session, redis_client, run_id=seeded_kb_with_short_expiry.run2_id,
        sanitized_query="What is the return window?", final_intent="return_policy",
        scope=agent_scope, release=active_release, now=t1
    )
    assert "expired_evidence" in res2.reason_codes

@pytest.mark.asyncio
async def test_conflicting_policy_documents_flagged(
    db_session, redis_client, seeded_conflicting_kb, agent_scope, active_release
):
    now = datetime(2026, 10, 29, 9, 0, 0, tzinfo=timezone.utc)
    res = await retrieve_evidence(
        db_session, redis_client, run_id=seeded_conflicting_kb.run_id,
        sanitized_query="How many days for refund?", final_intent="refund_policy",
        scope=agent_scope, release=active_release, now=now
    )
    assert "conflicting_evidence" in res.reason_codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/evaluation/test_retrieval_and_evidence_validity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.retrieval'`

- [ ] **Step 3: Implement `knowledge` schema, hybrid search (FTS + vector cosine), validity/conflict detector, and cache re-validation**

1. Create `db/migrations/knowledge/001_knowledge_documents.sql` with `knowledge.documents` and `knowledge.document_versions (id, document_id, version, policy_key, normalized_rule_value, valid_from, valid_to, status, allowed_roles, content_hash, sanitized_excerpt, search_tsv)`.
2. Implement `retrieval/service.py` filtering by `allowed_roles` and `status == 'approved'` before top-3 ranking, checking `valid_from <= now < valid_to` both on DB reads and after Redis cache hits, detecting conflicting `normalized_rule_value` on overlapping `policy_key` intervals (`conflicting_evidence`), and persisting immutable `app.evidence_snapshots`.
3. Implement `retrieval/validator.py` so `Task 5` re-validates both knowledge `valid_to` and business order `version` at approve and send time.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/evaluation/test_retrieval_and_evidence_validity.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add db/migrations/knowledge/001_knowledge_documents.sql data/knowledge/approved_kb.v1.json apps/core-backend/src/modules/retrieval tests/evaluation/test_retrieval_and_evidence_validity.py
git commit -m "feat(retrieval): implement scoped hybrid search, conflict detection, and cache validity recheck"
```

---

### Task 9 (CORE-09): Soạn Bản nháp LLM, Egress Proxy Allowlist & Xác thực Trích dẫn (Citation Validation)

**Owner:** Phạm Gia Bách | **Reviewer:** Nguyễn Công Phúc | **Milestone:** M2

**Files:**
- Create: `apps/core-backend/config/prompts/draft_prompt.v1.json`
- Create: `services/egress-proxy/config/squid.conf`
- Create: `apps/core-backend/src/modules/llm/schemas.py`
- Create: `apps/core-backend/src/modules/llm/builder.py`
- Create: `apps/core-backend/src/modules/llm/validator.py`
- Create: `apps/core-backend/src/modules/llm/client.py`
- Test: `tests/security/test_llm_egress_and_citation_validation.py`

**Interfaces:**
- Consumes: `privacy.scanner.scan_and_mask_text`, `app.evidence_snapshots`, `EGRESS_PROXY_URL`.
- Produces:
  - `llm.builder.build_egress_payload(sanitized_question: str, final_intent: str, evidence: list[Evidence], prompt_version: str) -> dict[str, Any]`
  - `llm.validator.validate_llm_output(raw_output: str, allowed_citation_ids: set[str], run_id: UUID) -> ValidatedDraft(body: str, citation_ids: list[str])` (ném `InvalidLlmOutputError` nếu JSON sai schema `{body, citation_ids}`, `citation_ids` rỗng, chứa ID ngoài `allowed_citation_ids`, chứa URL/markdown link hoặc tool call, hoặc chứa PII thô).
  - `llm.client.call_via_proxy(payload: dict[str, Any], remaining_budget_sec: float, idempotency_key: str) -> LlmCallOutcome`

- [ ] **Step 1: Write the failing test**

Create `tests/security/test_llm_egress_and_citation_validation.py` including **Review Focus #2** (`test_call_via_proxy_timeout_marks_outcome_unknown`):
```python
import uuid
import pytest
from src.modules.llm.validator import validate_llm_output, InvalidLlmOutputError
from src.modules.llm.client import compute_attempt_timeout

def test_validate_llm_output_rejects_foreign_citations_and_urls():
    run_id = uuid.uuid4()
    allowed = {"cit_kb_1", "cit_ord_1"}

    # Valid output passes
    valid = validate_llm_output(
        '{"body": "Orders ship within 2 business days [cit_kb_1].", "citation_ids": ["cit_kb_1"]}',
        allowed_citation_ids=allowed,
        run_id=run_id,
    )
    assert valid.citation_ids == ["cit_kb_1"]

    # Hallucinated citation ID fails
    with pytest.raises(InvalidLlmOutputError):
        validate_llm_output(
            '{"body": "Refund approved.", "citation_ids": ["cit_fake_99"]}',
            allowed_citation_ids=allowed,
            run_id=run_id,
        )

    # Embedded external URL fails
    with pytest.raises(InvalidLlmOutputError):
        validate_llm_output(
            '{"body": "Visit https://evil.example.com to claim refund.", "citation_ids": ["cit_kb_1"]}',
            allowed_citation_ids=allowed,
            run_id=run_id,
        )

def test_compute_attempt_timeout_respects_8s_cap_and_remaining_budget():
    assert compute_attempt_timeout(remaining_budget_sec=10.5) == 8.0
    assert compute_attempt_timeout(remaining_budget_sec=4.2) == 4.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/security/test_llm_egress_and_citation_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.llm'`

- [ ] **Step 3: Implement prompt builder, strict output/citation validator, proxy-only HTTP client, and Squid allowlist config**

1. Create `apps/core-backend/config/prompts/draft_prompt.v1.json` separating system instructions from untrusted customer text/evidence blocks.
2. Implement `llm/validator.py` and `llm/client.py` routing all traffic exclusively via `EGRESS_PROXY_URL` with `follow_redirects=False`, timeout `min(8.0, remaining_budget_sec)`, and strict `outcome_unknown` classification when a read timeout occurs after request transmission.
3. Create `services/egress-proxy/config/squid.conf` allowing only HTTPS port 443 to the configured LLM provider host and disabling request/response body logging.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/security/test_llm_egress_and_citation_validation.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core-backend/config/prompts/draft_prompt.v1.json services/egress-proxy/config/squid.conf apps/core-backend/src/modules/llm tests/security/test_llm_egress_and_citation_validation.py
git commit -m "feat(llm): add prompt builder, citation/URL validator, and proxy-only egress client"
```

---

### Task 10 (CORE-10): Phục hồi Trạng thái qua REST, WebSocket Notifications & Kịch bản E2E

**Owner:** An Đức Minh Trí | **Reviewer:** Phạm Gia Bách | **Milestone:** M3

**Files:**
- Create: `apps/core-backend/src/websocket.py`
- Modify: `apps/core-backend/src/main.py`
- Test: `tests/e2e/test_rest_recovery_and_websocket.py`

**Interfaces:**
- Consumes: `auth.service.authenticate_request(require_fresh_db=True)`, `tickets.service.get_ticket_for_actor`.
- Produces:
  - WebSocket endpoint `/api/v1/ws`: Yêu cầu frame xác thực đầu tiên `{"type": "auth", "access_token": "..."}` trong vòng 5 giây; kiểm tra `Origin` và quyền DB trên từng `ticket_id` / `run_id` khi subscribe; chỉ phát frame `{"event": "ticket.changed" | "run.changed", "resource_id": "...", "version": int, "occurred_at": "..."}` (không chứa PII hay nội dung draft).
  - `websocket.notify_resource_changed(event: Literal["ticket.changed", "run.changed"], resource_id: UUID, version: int) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_rest_recovery_and_websocket.py` covering **Review Focus #1** and **Review Focus #3** (`test_ws_disconnects_on_role_revocation`):
```python
import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_staff_reload_recovery_via_ticket_pointers(
    client: AsyncClient, agent_token: str, assigned_ticket_with_draft
):
    t_id = assigned_ticket_with_draft["ticket_id"]
    draft_id = assigned_ticket_with_draft["draft_id"]

    # Staff approves draft -> network drops before send; browser reloads with empty state
    dec_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={"source": "ai", "action": "approve", "draft_id": draft_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'},
    )
    assert dec_res.status_code == 201
    expected_dec_id = dec_res.json()["data"]["id"]

    # On reload, staff GETs ticket and recovers current_decision_id & ETag
    t_get = await client.get(f"/api/v1/tickets/{t_id}", headers={"Authorization": f"Bearer {agent_token}"})
    assert t_get.status_code == 200
    assert t_get.json()["data"]["current_decision_id"] == expected_dec_id
    etag = t_get.headers["ETag"]

    # Staff completes send using recovered pointer
    send_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": expected_dec_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": etag},
    )
    assert send_res.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_rest_recovery_and_websocket.py -v`
Expected: FAIL until WebSocket auth/subscription and pointer recovery E2E are wired

- [ ] **Step 3: Implement `/api/v1/ws` first-frame auth, DB-checked subscription manager, and E2E recovery flow**

1. Create `apps/core-backend/src/websocket.py` enforcing 5-second timeout for first auth frame, Origin validation, DB-backed `role_version` and ticket/run scope verification on subscribe and before broadcasting events, and immediate disconnect when `invalidate_user_sessions` fires.
2. Wire `notify_resource_changed` after DB commit in `tickets`, `orchestration`, and `review` routes.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/e2e/test_rest_recovery_and_websocket.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/core-backend/src/websocket.py apps/core-backend/src/main.py tests/e2e/test_rest_recovery_and_websocket.py
git commit -m "feat(ws,e2e): add first-frame authenticated WebSocket notifications and REST recovery E2E"
```

---

### Task 11 (CORE-11): Ghép Hạ tầng Đa Replica (2 API Replica + LB + Isolation Networks) & Runbook Vận hành

**Owner:** Đoàn Anh Minh | **Reviewer:** Phạm Gia Bách | **Milestone:** M3

**Files:**
- Create: `infra/compose/docker-compose.yml`
- Create: `infra/edge/nginx.conf`
- Create: `infra/ml-balancer/nginx.conf`
- Create: `infra/cache/redis.conf`
- Create: `infra/secrets/.env.example`
- Create: `docs/core-backend-runbook.md`
- Test: `tests/security/test_network_and_replica_resilience.py`

**Interfaces:**
- Consumes: Container entrypoints của `core-api`, `ai-worker`, `pii-resolver`, `ml-inference`, `egress-proxy`.
- Produces:
  - Mạng Docker tách biệt: `edge_net` (Gateway + Core API x2), `core_net` (Core API + Worker + Redis + Postgres), `vault_net` (Worker/API -> Resolver -> Postgres `vault`), `ml_net` (Worker -> ML LB -> ML Inference), `egress_net` (Worker -> Egress Proxy -> Internet; `ai-worker` thuộc `internal: true` network và chỉ đi ra ngoài qua `egress-proxy`).

- [ ] **Step 1: Write the failing test**

Create `tests/security/test_network_and_replica_resilience.py`:
```python
from pathlib import Path
import yaml

def test_compose_enforces_two_api_replicas_and_internal_worker_network():
    compose = yaml.safe_load(Path("infra/compose/docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "core-api-1" in services and "core-api-2" in services
    assert "ai-worker" in services
    assert "pii-resolver" in services
    assert "egress-proxy" in services

    # Worker must not receive VAULT_DB_URL
    worker_env = services["ai-worker"].get("environment", {})
    assert "VAULT_DB_URL" not in worker_env
    assert "VAULT_DB_URL" in services["pii-resolver"].get("environment", {})

    # Core internal network must be marked internal: true so worker cannot bypass egress-proxy
    assert compose["networks"]["core_net"]["internal"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/security/test_network_and_replica_resilience.py -v`
Expected: FAIL with `FileNotFoundError: infra/compose/docker-compose.yml`

- [ ] **Step 3: Implement multi-replica Docker Compose, Nginx LB configs, Redis memory cap, and Runbook**

1. Create `infra/compose/docker-compose.yml` with total memory limits fitting within `<= 5 GB RAM` on an 8 GB host, 2 stateless `core-api` replicas behind `infra/edge/nginx.conf`, isolated networks (`core_net` with `internal: true`), and distinct DB role URLs per service.
2. Create `infra/cache/redis.conf` (`maxmemory 256mb`, `maxmemory-policy allkeys-lru`) and `docs/core-backend-runbook.md` documenting startup, migrations, seed, smoke checks, and replica failover.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/security/test_network_and_replica_resilience.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infra/compose/docker-compose.yml infra/edge/nginx.conf infra/ml-balancer/nginx.conf infra/cache/redis.conf infra/secrets/.env.example docs/core-backend-runbook.md tests/security/test_network_and_replica_resilience.py
git commit -m "feat(infra): configure 2-replica API stack, internal worker network, and operational runbook"
```

---

### Task 12 (CORE-12): Ghép Toàn bộ Pipeline AI, Kiểm thử Chịu lỗi (Chaos/Failure Matrix) & Load Test (NFR-08)

**Owner:** Nguyễn Công Phúc | **Reviewer:** An Đức Minh Trí | **Milestone:** M3

**Files:**
- Create: `apps/core-backend/src/modules/orchestration/pipeline_runner.py`
- Create: `tests/integration/test_full_ai_pipeline_and_failures.py`
- Create: `tests/performance/load_test.py`
- Create: `docs/core-backend-verification.md`

**Interfaces:**
- Consumes: `privacy.client.sanitize_for_run` (Task 6), `intent.client.classify_intent` & `escalation.service.evaluate_intent_gates` (Task 7), `retrieval.service.retrieve_evidence` (Task 8), `llm.builder.build_egress_payload`, `llm.client.call_via_proxy` & `llm.validator.validate_llm_output` (Task 9).
- Produces:
  - `orchestration.pipeline_runner.execute_pipeline_job(session: AsyncSession, redis: Redis, job: ClaimedJob) -> None`
  - `orchestration.pipeline_runner.execute_egress_job(session: AsyncSession, job: ClaimedJob) -> None`
  - Script đo tải `tests/performance/load_test.py` kiểm chứng $\ge 5$ phiên đồng thời, $p50 \le 4\text{s}$, $p95 \le 12\text{s}$, error rate $\le 1\%$ và báo cáo nghiệm thu `docs/core-backend-verification.md`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_full_ai_pipeline_and_failures.py`:
```python
import pytest
from src.modules.orchestration.pipeline_runner import execute_pipeline_job, execute_egress_job
from src.modules.orchestration.worker import claim_next_job

@pytest.mark.asyncio
async def test_end_to_end_pipeline_creates_grounded_draft_without_auto_reply(
    db_session, redis_client, queued_order_tracking_run
):
    run_id = queued_order_tracking_run.id
    p_job = await claim_next_job(db_session, stage="pipeline", worker_id="w1")
    await execute_pipeline_job(db_session, redis_client, p_job)

    e_job = await claim_next_job(db_session, stage="llm_egress", worker_id="w2")
    assert e_job is not None
    await execute_egress_job(db_session, e_job)

    await db_session.refresh(queued_order_tracking_run)
    assert queued_order_tracking_run.status == "awaiting_review"
    assert queued_order_tracking_run.draft is not None
    assert len(queued_order_tracking_run.draft.citation_ids) >= 1
    # Invariant #1: Worker never creates a public reply
    from sqlalchemy import select, func
    from src.modules.review.models import ReplyModel
    reply_count = await db_session.scalar(
        select(func.count()).select_from(ReplyModel).where(ReplyModel.ticket_id == queued_order_tracking_run.ticket_id)
    )
    assert reply_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_full_ai_pipeline_and_failures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.orchestration.pipeline_runner'`

- [ ] **Step 3: Implement `pipeline_runner.py`, failure injection tests, and concurrent load test script**

1. Implement `apps/core-backend/src/modules/orchestration/pipeline_runner.py` chaining `sanitize_for_run` -> `classify_intent` -> `evaluate_intent_gates` -> `retrieve_evidence` -> `build_egress_payload` -> `complete_pipeline_stage_and_enqueue_egress`, and `execute_egress_job` chaining `call_via_proxy` -> `validate_llm_output` -> `commit_run_draft` with atomic audit events at each transition.
2. Implement `tests/performance/load_test.py` measuring true end-to-end AI latency (from `POST /runs` acceptance until `status in ("awaiting_review", "escalated")`, separating draft completion latency from fallback latency) across 1 user vs 5 concurrent sessions, and record results in `docs/core-backend-verification.md`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_full_ai_pipeline_and_failures.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/core-backend/src/modules/orchestration/pipeline_runner.py tests/integration/test_full_ai_pipeline_and_failures.py tests/performance/load_test.py docs/core-backend-verification.md
git commit -m "feat(pipeline): wire full AI worker pipeline, resilience matrix, and load test harness"
```
