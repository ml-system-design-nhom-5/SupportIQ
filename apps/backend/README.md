# SupportIQ application backend

FastAPI owns sessions, commerce views and customer-created demo orders, tickets, suggestions, human decisions, and audit events. It serves the production React build on the same origin. Existing model training and evaluation code is unchanged.

From the repository root on Windows:

```powershell
.\scripts\start-app.ps1
```

Open `http://127.0.0.1:8080`. The command uses installed PostgreSQL binaries to create a separate, loopback-only cluster on port 55432. It never changes the existing PostgreSQL Windows service. Set `SUPPORTIQ_PG_BIN` to the installed `bin` directory when discovery cannot find it. PostgreSQL's command-line tools cannot handle this repository's Unicode path on every Windows installation, so the cluster lives under `%LOCALAPPDATA%/SupportIQ/<workspace hash>/postgres`; `.local/postgres-location.json` records its location.

The first run generates passwords in `.local/application.json`. Login names are `customer-1`, `staff-1`, `manager-1`, and `admin-1`. Other customer accounts follow source customer IDs in first-occurrence order. Passwords are not committed or returned by an API. `customer-1` owns the 15 orders of `demo-customer`.

```powershell
# Database preparation only; useful before running integration tests.
.\scripts\start-app.ps1 -SetupOnly
# Run the application without loading AI models.
.\scripts\start-app.ps1 -WithoutAI
# Use an existing environment and production build.
.\scripts\start-app.ps1 -SkipInstall -SkipBuild
# Enable external generation using GEMINI_API_KEY from the local .env.
.\scripts\start-app.ps1 -EnableLLM
# Stop only the recorded application processes.
.\scripts\stop-app.ps1
# Also stop this workspace's PostgreSQL cluster, preserving all data.
.\scripts\stop-app.ps1 -StopDatabase
```

The AI gateway loads existing verified DistilBERT and cached BGE assets offline. The Python environment needs the existing ML dependencies (`pipeline/requirements-transformers.txt`). Missing assets leave manual handling available. External generation is enabled with a configured Gemini key; `-DisableLLM` disables it. The existing classifier exposes uncalibrated softmax scores: the console labels them Raw score, and the gateway uses the existing per-intent confidence and margin thresholds, without relabeling raw scores as calibrated probabilities. No calibrated probabilities are fabricated.

## API and safeguards

The generated description of the implemented API is `contracts/backend.openapi.json`; interactive API docs are at `/api/docs`. The design reference is [contracts v1](../../docs/design/contracts-v1.md), whose revision 2 is still in review.

- `accounts/`: Argon2id passwords, hashed opaque cookie sessions, idle and absolute expiry, persistent sign-in throttling, internal-account changes and session revocation.
- `commerce/`: customer-owned, read-only projections. See [data mapping](../../docs/guides/application-windows.md#source-data).
- `tickets/`: sticky authority, proposals, escalations, one human-sent reply, warning acknowledgement, stale-suggestion checks, placeholders, leased jobs, privacy, and reports.
- `platform/`: typed settings, SQLAlchemy records, transaction-scoped idempotency locks and append-only audit records.
- `migrations/`: explicit Alembic migrations. Replicas never migrate or seed at startup. `python -m apps.backend.manage initialize` runs the initial migration and deterministic source import.

The runtime role can insert customer-created orders but cannot change catalog products and no audit/message updates or deletes. PostgreSQL triggers also protect immutable messages, audit events, sticky authority and restricted role changes. Application writes carry an Origin check and, except session operations, an Idempotency-Key.

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest tests/application -q
.venv\Scripts\python.exe -X utf8 -m pytest -q
```

Integration tests use a uniquely named schema on the isolated project cluster and remove only that schema. They never reset the application's data. Confidential values are omitted from request logs and SQL error responses.
