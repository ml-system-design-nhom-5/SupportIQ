# SupportIQ

SupportIQ is an AI copilot for e-commerce support. Customers use a read-only demo shop; staff review intent, sources and replies; managers handle cases that need authority; administrators manage internal accounts. A person sends every reply. Commerce data comes from `data/knowledge/mock_orders.json`.

## Run on Windows

```powershell
.\scripts\start-app.ps1
```

Open **http://127.0.0.1:8080**. No Docker is required. The first run installs application dependencies, prepares a separate native PostgreSQL cluster, imports synthetic orders, builds React and starts the application. PostgreSQL binaries, Node 22+, pnpm and Python must be installed. The existing model environment is needed for AI; use `-WithoutAI` otherwise.

Login names: `customer-1`, `staff-1`, `manager-1`, `admin-1`. Generated passwords are in the ignored `.local/application.json`. Customer 1 owns the 15 orders of `demo-customer`. No passwords are committed.

External LLM generation is enabled when a Gemini key is configured; use `-DisableLLM` to disable it. To enable it with your local `GEMINI_API_KEY`, run `./scripts/start-app.ps1 -EnableLLM`. Local model inference and retrieval use the existing verified assets. The model exposes raw softmax scores. Draft routing uses the existing per-intent score and margin thresholds; uncertain requests still require intent confirmation.

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
- [Existing core architecture](docs/ARCHITECTURE.md) and [core backend design](docs/superpowers/specs/2026-10-27-core-backend-design.md).

The source design is the documentation on `chore/fe-be-supportiq-ecom` at `48caf66`. Contracts v1 revision 2 remains in review; this implementation does not change that approval status. Native runtime instructions describe the running application; proposed multi-replica hosting remains separate release work.

## Checks

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest -q
cd apps/frontend
pnpm build
pnpm test
pnpm test:e2e
```

End-to-end tests require the native application to be running and use Microsoft Edge. They create synthetic tickets in the local demonstration database. See each component README for test setup and limitations.
