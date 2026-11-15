# Docker Compose Runtime Guide

SupportIQ provides a Linux Docker Compose stack alongside (and isolated from) the native Windows setup.

## Architecture & Isolation

- **`postgres` (`postgres:16-alpine`)**: Internal network only (no published host ports). Stores state in named volume `pgdata` under owner role `supportiq_owner`.
- **`init` (one-shot, `restart: "no"`)**: Runs `python -m apps.backend.docker_init init` after `postgres` is healthy. Validates required runtime secrets, provisions/updates restricted `supportiq_app` role (`NOSUPERUSER NOCREATEDB NOCREATEROLE`), writes container-local secrets to `/run/supportiq/application.json` (never touching host `.local/application.json`), runs Alembic migrations (`alembic upgrade head`), applies least-privilege table/sequence `GRANT`s, and seeds synthetic orders/accounts **only when the `accounts` table is empty** (first start).
- **`ai-service` (non-root Python 3.12-slim + CPU PyTorch)**: Internal network only (`8002`). Mounts verified Fit2 classifier + calibration read-only (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113`) and host Hugging Face cache read-only (`BAAI/bge-small-en-v1.5`) with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. Defaults to `gemini-3.5-flash-lite` (`SUPPORTIQ_ENABLE_LLM=true`, `SUPPORTIQ_MAX_LIVE_LLM_REQUESTS=2`, `SUPPORTIQ_LLM_MAX_ATTEMPTS=1`, runtime `GEMINI_API_KEY`). Healthcheck asserts `status == "ready"`, `retrieval_ready == true`, `model_verified == true`, and pinned Fit2/calibration SHA-256 digests.
- **`backend` (non-root Python 3.12-slim + multi-stage Node 24 / pnpm 10 SPA)**: Waits for `init` completion and healthy `ai-service`. Connects strictly as `supportiq_app` via URL-escaped DSN, enforces strict spaCy NER (`SUPPORTIQ_REQUIRE_PRIVACY_NER=true`), and binds **only** `127.0.0.1:${SUPPORTIQ_HOST_PORT:-8081}:8080` so native `:8080` can run simultaneously.

## Prerequisites & Offline Model Cache

1. **Verified Fit2 weights** must exist locally at `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/`.
2. **Existing Hugging Face cache** for `BAAI/bge-small-en-v1.5` must already be present on the host (`~/.cache/huggingface` on Linux or `C:/Users/<you>/.cache/huggingface` on Windows). Containers never download model weights at runtime.
   - If you need to isolate a copy from your existing host cache without mutating it:
     - **PowerShell:** `Copy-Item -Recurse "$env:USERPROFILE\.cache\huggingface\hub\models--BAAI--bge-small-en-v1.5" ".\.local\hf-cache\hub\"`
     - **Linux:** Ensure read/execute permissions (`chmod -R a+rX`) on the mounted HF cache directory if host UID differs from container UID `10001`.

## Configuration & Startup

```bash
cp .env.docker.example .env.docker
# Edit .env.docker: set strong distinct owner/app Postgres passwords,
# demo account passwords, SUPPORTIQ_HF_CACHE_DIR, and optional GEMINI_API_KEY.

docker compose --env-file .env.docker up -d --build
```

Open **http://127.0.0.1:8081**. Subsequent `docker compose --env-file .env.docker up -d` or container restarts preserve database rows, sessions/tickets/orders, and profile updates; `seed()` runs only on an empty `accounts` table.

Stop cleanly without removing database state:

```bash
docker compose --env-file .env.docker down
```

## Verified on 2026-11-15

- Both image targets built on Docker Desktop's Linux engine; 8 focused packaging tests passed.
- PostgreSQL, AI and backend became healthy; initialization exited successfully. Backend and AI run as UID 10001, and backend connects as the restricted `supportiq_app` role.
- Fit2 and calibration matched the pinned digests; retrieval and privacy NER were ready, with Gemini enabled and configured.
- Playwright verified a customer request for a human agent, staff workspace, administrator reply and customer receipt without JavaScript errors. This verifies the human support flow; live Gemini drafting was not exercised in this check.
- A complete `down` / `up` preserved database row counts and the full saved ticket content. The native Windows application remained ready on port 8080.

Check startup explicitly with `docker compose --env-file .env.docker up -d --wait --wait-timeout 180` and `docker compose --env-file .env.docker ps -a`. Keep `.env.docker` private; it contains the Docker account passwords and API key. Avoid `down -v` unless intentionally deleting the Docker database.

The 2-request LLM cap is per AI process and resets when that process restarts; it is not a persistent spending limit. Once exhausted, drafting falls back to manual handling. Restarts do not grant additional evaluation spending authorization.
