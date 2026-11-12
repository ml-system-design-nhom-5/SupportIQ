# SupportIQ Core Backend Operational Runbook

## 1. System Overview & Architecture

SupportIQ Core Backend is a modular monolith structured around 4 distinct PostgreSQL database schemas and isolated networks:

- **Edge Layer:** Nginx reverse proxy load-balancing requests across two stateless API replicas (`core-api-1` and `core-api-2`), terminating HTTP/WebSocket traffic.
- **Core API Replicas:** Stateless FastAPI application instances handling client authentication, commerce, tickets, audit queries, and websocket notifications.
- **AI Worker (`ai-worker`):** Autonomous background consumer executing durable jobs (`pipeline` -> `llm_egress`) with strict 12-second lease deadlines. Runs in an internal network without direct internet access.
- **PII Resolver (`pii-resolver`):** Isolated micro-service holding sole credentials to PostgreSQL `vault` schema, translating tokens to masked text and resolving tokens only for verified authorized staff deliveries.
- **Egress Proxy (`egress-proxy`):** Forward proxy allowing only port 443 outbound HTTPS traffic to approved LLM provider domains (`api.openai.com`, `api.anthropic.com`).
- **Data Stores:**
  - **PostgreSQL 16:** Segregated into 4 schemas (`app`, `knowledge`, `audit`, `vault`) with dedicated role-based access.
  - **Redis 7:** Enforces 256 MB memory cap with `allkeys-lru` eviction policy for caching and rate limiting.

---

## 2. Environment Configuration

Copy the example environment file and set secure secrets:

```bash
cp infra/secrets/.env.example .env
```

Ensure `APP_ENCRYPTION_KEY` is a 64-character hexadecimal key (256 bits).
Ensure `JWT_SECRET_KEY` and `INTERNAL_SERVICE_TOKEN` are high-entropy strings.

---

## 3. Database Migration & Initialization

Apply SQL migrations in sequence across schemas:

1. `db/migrations/app/000_init_schemas_and_roles.sql`
2. `db/migrations/app/001_idempotency_records.sql`
3. `db/migrations/app/002_users_and_sessions.sql`
4. `db/migrations/app/003_commerce_and_tickets.sql`
5. `db/migrations/app/004_releases_runs_jobs_and_attempts.sql`
6. `db/migrations/app/005_decisions_and_replies.sql`
7. `db/migrations/audit/001_audit_events.sql`
8. `db/migrations/token-vault/001_token_mappings.sql`
9. `db/migrations/knowledge/001_knowledge_documents.sql`

Seed demo products and knowledge base documents:
```bash
python -m src.seed_demo_data
```

---

## 4. Starting and Stopping the Stack

### Launching the cluster:
```bash
docker compose -f infra/compose/docker-compose.yml up -d
```

### Checking running containers:
```bash
docker compose -f infra/compose/docker-compose.yml ps
```

### Viewing logs:
```bash
# Core API logs
docker compose -f infra/compose/docker-compose.yml logs -f core-api-1 core-api-2

# Worker processing logs
docker compose -f infra/compose/docker-compose.yml logs -f ai-worker

# Egress proxy traffic
docker compose -f infra/compose/docker-compose.yml logs -f egress-proxy
```

### Graceful shutdown:
```bash
docker compose -f infra/compose/docker-compose.yml down
```

---

## 5. Health Checks and Smoke Testing

### Liveness Probe (Requires Internal Token):
```bash
curl -H "Authorization: Bearer <INTERNAL_SERVICE_TOKEN>" http://localhost/api/v1/health/live
# Expected: {"data": {"status": "ok", "ai_available": false}}
```

### Readiness Probe:
```bash
curl -H "Authorization: Bearer <INTERNAL_SERVICE_TOKEN>" http://localhost/api/v1/health/ready
# Expected: {"data": {"status": "ok"}}
```

---

## 6. Replica Failover Verification

1. Stop replica 1:
   ```bash
   docker stop supportiq-core-api-1
   ```
2. Verify traffic continues transparently via replica 2:
   ```bash
   curl -i http://localhost/api/v1/health/ready -H "Authorization: Bearer <INTERNAL_SERVICE_TOKEN>"
   ```
   Status must remain 200 OK.
3. Restart replica 1:
   ```bash
   docker start supportiq-core-api-1
   ```
   Nginx automatically resumes routing traffic to both replicas via `least_conn`.

---

## 7. Security & Privacy Incident Response

- **Worker Compromise:** Because `ai-worker` runs inside `core_net` (`internal: true`) without `VAULT_DB_URL`, attackers cannot access raw customer PII in `vault.token_mappings`.
- **Egress Exfiltration:** All outbound worker traffic must pass through `egress-proxy`. Non-whitelisted outbound destinations are blocked with 403 Forbidden.
- **Audit Tampering:** `audit.events` is protected by append-only triggers. Attempted `UPDATE` or `DELETE` queries are aborted by the database engine.
