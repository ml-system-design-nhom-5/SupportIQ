# SupportIQ

SupportIQ is an AI copilot for e-commerce customer support. Customers submit support requests; staff review predicted intents, sources, and response drafts; managers handle authority-required cases; administrators manage internal accounts. A human agent reviews and sends every reply. Simulated commerce data comes from `data/knowledge/mock_orders.json`.

## Run on Windows

```powershell
.\scripts\start-app.ps1
```

Open **http://127.0.0.1:8080**. No Docker is required. The startup script dynamically discovers installed PostgreSQL binaries, verifies the runtime driver via preflight (`scripts/native_runtime.py preflight`), configures `PSYCOPG_IMPL=python` for Windows Application Control environments, prepares a dedicated native PostgreSQL cluster, seeds synthetic orders, builds the React frontend, and starts the application services.

PostgreSQL binaries, Node 22+, pnpm, and Python must be installed. The existing model environment is needed for AI; use `-WithoutAI` otherwise.

Login names: `customer-1`, `staff-1`, `manager-1`, `admin-1`. Generated passwords are in the ignored `.local/application.json`. Customer 1 owns the 15 orders of `demo-customer`. No passwords are committed.

External LLM generation is enabled when a Gemini key is configured; use `-DisableLLM` to disable it. Local model inference and retrieval use the existing verified assets. The model exposes raw softmax scores. Draft routing uses the existing per-intent score and margin thresholds; uncertain requests still require intent confirmation.

Stop with `./scripts/stop-app.ps1`. Add `-StopDatabase` to stop the workspace database while preserving its data. See [Windows setup and source-data mappings](docs/guides/application-windows.md).

## Application components

| Component | Responsibility |
|---|---|
| [apps/frontend](apps/frontend/README.md) | React/TypeScript shop, support console, manager reports and admin UI |
| [apps/backend](apps/backend/README.md) | FastAPI sessions, authorization, commerce views, ticket workflow, audit, idempotency and PostgreSQL |
| [apps/ai_service](apps/ai_service/README.md) | Stateless HTTP adapter for existing model, retrieval and optional Gemini generation |
| apps/ml_inference | Existing verified intent model |
| apps/core_backend | Existing inference/retrieval/LLM components and evaluation orchestration |
| [apps/demo](apps/demo/README.md) | Earlier local copilot demo, preserved |
| pipeline, scripts, tests | Existing training, evaluation and verification tools, preserved |

The frontend calls only the application backend. The backend enforces all roles and object access, and sends pseudonymized text plus identifier-free order fields to AI. The shop cannot expose drafts. Admin cannot reach customer records. Customers can create a single-item demo order from a product. No payment or refund is executed.

## Documentation

- [Requirements](docs/product/requirements.md), [accepted decisions](docs/decisions/README.md), and [approved screen designs](docs/design/console-ui.md).
- [Actual application API](contracts/backend.openapi.json), [design tokens](DESIGN.md), and [verification scope and limits](docs/guides/application-verification.md).
- [Existing core architecture](docs/ARCHITECTURE.md).

Native runtime instructions describe the running application; proposed multi-replica hosting remains separate release work.

## Checks

See the [application verification guide](docs/guides/application-verification.md) for current verification evidence and acceptance limits. The shared retrieval benchmark targets an older KB; its recall is not certified for the current application release.

```powershell
# Python unit and application tests
.venv\Scripts\python.exe -X utf8 -m pytest tests/unit tests/application -q

# Standalone preflight diagnostic
.venv\Scripts\python.exe scripts/native_runtime.py preflight

# Frontend build, unit tests (threads pool), and E2E
cd apps/frontend
pnpm build
pnpm test
pnpm test:e2e
```

End-to-end tests require the native application to be running and use Microsoft Edge. They create synthetic tickets in the local demonstration database. See each component README for test setup and limitations.
