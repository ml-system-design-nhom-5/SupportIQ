# Deploy

This guide sets up the demo on the free plans that [ADR-0016](../docs/decisions/0016-hosting-on-free-tiers.md) decides: the setup order, the settings of each platform, the checks before and after the first deploy, and what is still open. The parts and how they connect are in [ADR-0016, Overview](../docs/decisions/0016-hosting-on-free-tiers.md#overview).

This guide holds no real value: no URL, project reference, token, or password. Each secret lives only in the settings of the platform that uses it ([ADR-0016, Secrets](../docs/decisions/0016-hosting-on-free-tiers.md#secrets)).

## Setup order

1. **Supabase.** Create one free project in `ap-southeast-1` ([ADR-0016, PostgreSQL on Supabase](../docs/decisions/0016-hosting-on-free-tiers.md#postgresql-on-supabase)). Turn on "Enforce SSL on incoming connections" ([TLS to PostgreSQL](#tls-to-postgresql)). Run the [PostgreSQL checks](#postgresql-checks) and record their results.
2. **The app role.** In `backend/.env` on your machine, set `DATABASE_URL_OWNER` and `DATABASE_URL_APP` to the session pooler URLs of the two roles, without a query, and set `DATABASE_TLS` to `verify-full`, because `.env.example` sets `disable` for the local cluster ([TLS to PostgreSQL](#tls-to-postgresql)). Run `uv run backend create-app-role` in `backend/` ([backend README, Commands](../backend/README.md#commands)).
3. **Render.** Create one free web service in Singapore, built from `backend/Dockerfile`. Set `PORT` to `8000`, turn auto-deploy off, and create a deploy hook ([ADR-0016, `backend` on Render](../docs/decisions/0016-hosting-on-free-tiers.md#backend-on-render)). Enter the [Render settings](#render-settings).
4. **GitHub.** Add two repository secrets, which only the deploy workflow reads ([ADR-0016, Migrations and one-off commands](../docs/decisions/0016-hosting-on-free-tiers.md#migrations-and-one-off-commands), item 4):
   - `DEPLOY_DATABASE_URL_OWNER`: the session pooler URL of `supportiq_owner.<project-ref>`, port 5432, with the scheme `postgresql+asyncpg`, without a query ([TLS to PostgreSQL](#tls-to-postgresql));
   - `RENDER_DEPLOY_HOOK_URL`: the deploy hook URL as Render shows it, with its `key`.
5. **First deploy.** On GitHub, open Actions, select the workflow `deploy`, and run it on the branch `main`. It runs the jobs of `backend.yml` again, then `backend migrate` as the owner role, then calls the deploy hook with `ref` set to that commit. A failed job or a failed migration deploys nothing, and a run on another branch stops before the migration ([repository checks, What runs where](../docs/guides/repository-checks.md#what-runs-where)).
6. **Seed.** In `backend/.env` on your machine, set the four `SEED_PASSWORD_*` settings. Run `uv run backend seed` in `backend/`.
7. **Cloudflare Pages.** Create one Pages project and enter the [Pages settings](#cloudflare-pages-settings) ([ADR-0016, `frontend` and the ingress on Cloudflare Pages](../docs/decisions/0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages)).
8. **Grafana Cloud.** Create one free stack with 2 named Editors and 1 shared Viewer. Keep the Viewer's password in the team's password manager ([ADR-0016, Telemetry on Grafana Cloud](../docs/decisions/0016-hosting-on-free-tiers.md#telemetry-on-grafana-cloud)).
9. **UptimeRobot.** Create one monitor that sends `GET /health/ready` straight to the Render URL every 5 minutes, not through the Pages Function ([ADR-0016, `backend` on Render](../docs/decisions/0016-hosting-on-free-tiers.md#backend-on-render), item 5).
10. **Checks.** Work through the [first-deploy checklist](#first-deploy-checklist).

## TLS to PostgreSQL

Every connection to Supabase leaves the host that opens it, so it uses TLS ([SEC-28](../docs/rules/security-and-privacy.md#transport-and-runtime)):

1. In Supabase, open Database Settings, then SSL Configuration, and turn on "Enforce SSL on incoming connections". The database restarts for a few minutes, and the setting applies to the session pooler too. From then on, Supabase refuses every connection without TLS.
2. `DATABASE_TLS` is `verify-full` for every connection to Supabase. It is the default, so Render leaves it unset; the job `deploy-migrate` sets it in its environment; and `backend/.env` on your machine sets it, because `.env.example` sets `disable` for the local cluster.
3. With `verify-full`, `backend` requires a server certificate signed by the root authority of Supabase and checks that it names the host of the URL. The authority is `backend/certs/supabase-root-ca.crt`, the default of `DATABASE_CA_FILE`, relative to the working directory, so Render, the deploy workflow, and your machine set no authority ([backend README, TLS to the database](../backend/README.md#tls-to-the-database)). The image copies it, and the deploy workflow runs from the checkout of `backend/`. If Supabase replaces its authority, download the new one from Database Settings, SSL Configuration, and replace the file and its record in the backend README together.
4. No URL of the database holds a query: not `DATABASE_URL_APP` on Render, not the secret `DEPLOY_DATABASE_URL_OWNER`, and not the two URLs in `backend/.env`. A URL entered before this rule may still end with `?ssl=require`: remove the query on Render and in the secret before the next deploy. `backend` refuses any query at startup with a `settings.invalid` line that names the setting, never its value.

## Render settings

[backend/.env.example](../backend/.env.example) lists every setting with its meaning and default. Set these on Render; leave the others unset, so their defaults apply:

| Setting | Value |
|---|---|
| `DATABASE_URL_APP` | The session pooler URL of `supportiq_app.<project-ref>`, port 5432, without a query ([ADR-0016, PostgreSQL on Supabase](../docs/decisions/0016-hosting-on-free-tiers.md#postgresql-on-supabase), item 1; [TLS to PostgreSQL](#tls-to-postgresql)) |
| `ALLOWED_ORIGINS` | Only the production origin of the Pages project ([ADR-0016, `frontend` and the ingress on Cloudflare Pages](../docs/decisions/0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages), item 9) |
| `BACKEND_BUILD_VERSION` | The commit that Render deploys ([Open questions](#open-questions)) |
| `AI_SERVICE_BASE_URL`, `AI_SERVICE_TOKEN` | The values of the deployed `ai-service` ([Open questions](#open-questions)) |
| `TRACE_EXPORTER` | `none`, until `backend` has a setting for the OTLP authorization header ([Open questions](#open-questions)) |

Never set `DATABASE_URL_OWNER` on Render ([ADR-0016, `backend` on Render](../docs/decisions/0016-hosting-on-free-tiers.md#backend-on-render), item 3).

The Dockerfile installs with `uv sync --locked`, so the Render build uses `uv.lock`, and it downloads the named-entity model from github.com ([ADR-0017](../docs/decisions/0017-named-entity-model-from-its-release-url.md#decision), items 1 and 2).

## Cloudflare Pages settings

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `VITE_FRONTEND_BUILD_VERSION=$CF_PAGES_COMMIT_SHA pnpm run build` ([admin UI design](../docs/design/admin-ui.md#developer-details-in-the-admin-area)) |
| Build output directory | `dist`, the output of `vite build` |
| `NODE_VERSION` | `24.22.2` |
| Production branch | `main`, from the join with the AI and ML code on |
| Preview deployments | Off |
| When the daily Functions limit is used up | Fail closed |
| `VITE_BACKEND_WAKE_ORIGIN` | The Render origin ([backend wake-up design](../docs/design/backend-wake-up.md#rules)) |
| `VITE_DEV_MODE` | Unset, so dev mode is off in the build ([console UI design](../docs/design/console-ui.md#frontend-settings)) |
| The `backend` URL of the Pages Function | The Render URL. The Function and its setting are not on this branch yet ([Open questions](#open-questions)) |

## PostgreSQL checks

Run these when the project is created, before the first deploy ([ADR-0016, PostgreSQL on Supabase](../docs/decisions/0016-hosting-on-free-tiers.md#postgresql-on-supabase), item 3).

| Check | Result |
|---|---|
| Both roles log in through the session pooler | Not run yet |
| A connection without TLS is refused, after "Enforce SSL on incoming connections" is on | Not run yet |
| `psql` with `sslmode=verify-full` and the root authority of `backend/certs/` reaches the session pooler (`select 1`) | Passed on 2026-11-17 |
| The TLS handshake of Python with the root authority of `backend/certs/` passes for the session pooler: Python checks certificates more strictly than `psql` | Passed on 2026-11-17 |
| `backend migrate` with `DATABASE_TLS=verify-full` reaches the session pooler | Not run yet |
| The pool of `backend`, 5 connections plus 10 overflow, fits the pool size of `supportiq_app`, 15 by default | Not run yet |
| The PostgreSQL major version is 17, the version that CI tests | Not run yet |
| The keep-alive keeps the project out of the pause after 1 week without activity | Not run yet |

## First-deploy checklist

The checks of [ADR-0016, Validation](../docs/decisions/0016-hosting-on-free-tiers.md#validation), and two of later decisions.

| Check | Result |
|---|---|
| The workflow migrates before it calls the deploy hook, and Render shows the migrated commit as deployed | Not run yet |
| A failed migration deploys nothing | Not run yet |
| Sign-in sets the cookie on the Pages origin | Not run yet |
| A write with another `Origin` returns `403` | Not run yet |
| A trace of one request is visible in Grafana Cloud | Not run yet |
| The measurement of ADR-0016, Context, repeated through the Function of this deployment | Not run yet |
| With the keep-alive paused for 17 minutes, opening the app sends the wake request, and sign-in succeeds once `backend` runs ([backend wake-up design](../docs/design/backend-wake-up.md#testing-and-evaluation)) | Not run yet |
| The NFR-08 load test against the deployed demo, with the sign-in latency on the free instance | Not run yet |
| The suggestion progress stream stays open through the Function beyond 10 000 ms ([ADR-0022](../docs/decisions/0022-server-sent-events-for-suggestion-progress.md#decision), statement 8) | Not run yet |
| `backend` starts with the named-entity model, and its memory and the p95 of pseudonymization fit the free instance ([ADR-0017](../docs/decisions/0017-named-entity-model-from-its-release-url.md#validation)) | Not run yet |

## Removal of the application of `main`

[ADR-0021](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#removal-of-the-application-of-main) deletes `apps/backend`, `apps/frontend`, and `apps/demo` in step 6 of the join, once every row of its checklist names its proof. The proofs are recorded here, because an accepted ADR is not edited ([documentation handbook, ADRs](../docs/README.md#adrs)).

### Rows covered by existing tests

These rows are covered by the tests below (ADR-0021, Removal of the application of `main`, statement 3). Every row is also covered by the contract tests of `backend`: `backend/tests/contract/test_operations.py`, `backend/tests/contract/test_permissions.py`, and `backend/tests/contract/test_schemathesis.py`.

| Row of the checklist | Tests of `backend` | Tests of `frontend` |
|---|---|---|
| Sign-in and sessions | `backend/tests/integration/accounts/test_sign_in.py`, `backend/tests/integration/accounts/test_sessions.py`, `backend/tests/unit/accounts/test_sign_in.py`, `backend/tests/unit/accounts/test_session_rules.py`, `backend/tests/unit/accounts/test_session_use_cases.py` | `frontend/src/features/session/components/sign-in-page.test.tsx`, `frontend/src/features/session/components/require-session.test.tsx`, `frontend/src/features/session/components/sign-out-button.test.tsx`, `frontend/src/features/session/model/session.test.ts`, `frontend/e2e/session.spec.ts` |
| Shop: products, orders, customer tickets | `backend/tests/integration/commerce/test_shop.py`, `backend/tests/integration/tickets/test_create_shop_ticket.py`, `backend/tests/integration/tickets/test_read_shop_tickets.py`, `backend/tests/integration/tickets/test_idempotent_ticket_creation.py`, `backend/tests/unit/commerce/test_shop_use_cases.py`, `backend/tests/unit/tickets/test_shop_tickets.py` | `frontend/src/features/shop-catalog/components/products-page.test.tsx`, `frontend/src/features/shop-catalog/components/product-page.test.tsx`, `frontend/src/features/shop-orders/components/orders-page.test.tsx`, `frontend/src/features/shop-orders/components/order-page.test.tsx`, `frontend/src/features/shop-support/components/support-page.test.tsx`, `frontend/src/features/shop-support/components/order-support-section.test.tsx`, `frontend/src/features/shop-support/components/order-support-sending.test.tsx`, `frontend/e2e/shop-catalog.spec.ts`, `frontend/e2e/shop-order.spec.ts` |
| Admin: accounts, role and status changes | `backend/tests/integration/accounts/test_account_list.py`, `backend/tests/integration/accounts/test_account_changes.py`, `backend/tests/integration/accounts/test_account_creation.py`, `backend/tests/integration/accounts/test_password_reset.py`, `backend/tests/integration/accounts/test_account_change_concurrency.py`, `backend/tests/integration/guardrails/test_admin_boundary.py`, `backend/tests/unit/accounts/test_admin_rules.py`, `backend/tests/unit/accounts/test_admin_use_cases.py` | `frontend/src/features/admin-accounts/components/accounts-page.test.tsx`, `frontend/src/features/admin-accounts/components/accounts-page-changes.test.tsx`, `frontend/src/features/admin-accounts/components/account-dialogs.test.tsx`, `frontend/e2e/admin-accounts.spec.ts` |
| Admin: versions in use | `backend/tests/integration/suggestions/test_admin_versions.py`, `backend/tests/unit/suggestions/test_admin_versions.py` | `frontend/src/features/admin-versions/components/versions-page.test.tsx`, `frontend/src/features/admin-versions/model/versions-in-use.test.ts`, `frontend/e2e/admin-versions.spec.ts` |
| Console: ticket list, ticket, views, KB | `backend/tests/integration/tickets/test_console_queues.py`, `backend/tests/integration/tickets/test_console_workspace.py`, `backend/tests/integration/tickets/test_console_ticket_view.py`, `backend/tests/integration/suggestions/test_console_kb_document_version.py`, `backend/tests/unit/tickets/test_console_use_cases.py`, `backend/tests/unit/tickets/test_console_views.py`, `backend/tests/unit/suggestions/test_kb_document_version_read.py` | `frontend/src/features/console-tickets/components/ticket-inbox.test.tsx`, `frontend/src/features/console-tickets/components/ticket-workspace-page.test.tsx`, `frontend/src/features/console-tickets/components/ticket-workspace-sources.test.tsx`, `frontend/src/features/console-tickets/model/kb-document.test.ts`, `frontend/e2e/console-workspace.spec.ts` |
| Reports | `backend/tests/integration/reports/test_console_report_figures.py`, `backend/tests/integration/reports/test_console_report_ai_figures.py`, `backend/tests/integration/reports/test_console_report_requests.py`, `backend/tests/integration/guardrails/test_report_holds_no_customer_data.py`, `backend/tests/unit/reports/test_console_report.py`, `backend/tests/unit/reports/test_report_rules.py` | `frontend/src/features/console-reports/components/reports-page.test.tsx`, `frontend/src/features/console-reports/model/report.test.ts`, `frontend/src/features/console-reports/model/reports-access.test.ts`, `frontend/e2e/console-reports.spec.ts` |

### Runs with the real AI

Each row below is run by hand against the Modal deployment of [ADR-0018](../docs/decisions/0018-hosting-of-ai-service-on-modal.md), because CI never calls an LLM (ADR-0021, Removal of the application of `main`, statement 1). A row that needs a draft with a policy citation runs only after a new KB version is admitted (statement 2).

| Row of the checklist | Date | Commit | `release_id` | Steps | Result |
|---|---|---|---|---|---|
| Suggestions and drafts in the console; `apps/demo` (running the pipeline, feedback, history) | | | | | Not run yet |
| FR-04, FR-06, FR-07, FR-09 | | | | | Not run yet |

## Every month

Check that the Render free hours, the Functions requests, the database size, and the Grafana Cloud usage stay within the free limits ([ADR-0016, Validation](../docs/decisions/0016-hosting-on-free-tiers.md#validation)).

## Roll back

Call the deploy hook with `ref` set to the previous commit. Every migration keeps the previous release working, so the database stays as it is ([ADR-0016, Migrations and one-off commands](../docs/decisions/0016-hosting-on-free-tiers.md#migrations-and-one-off-commands), item 5).

## Open questions

- `backend` has no setting for the OTLP authorization header yet ([ADR-0016, Follow-ups](../docs/decisions/0016-hosting-on-free-tiers.md#follow-ups)). Until it has, traces stay off on Render.
- Which variable of Render fills `BACKEND_BUILD_VERSION` with the deployed commit.
- The Pages Function, `_routes.json`, and the setting of the `backend` URL are on the branch `build/console-ui`: link after the merge of build/console-ui.
- Where `ai-service` runs, and so the values of `AI_SERVICE_BASE_URL` and `AI_SERVICE_TOKEN` ([ADR-0016, Open questions](../docs/decisions/0016-hosting-on-free-tiers.md#open-questions)).
- Whether `backend` accepts only requests that come through the Function, and how the per-client rate limit is enforced ([ADR-0016, Open questions](../docs/decisions/0016-hosting-on-free-tiers.md#open-questions)).
- Whether the free tier of Grafana Cloud offers the Singapore region at sign-up ([ADR-0016, Platforms](../docs/decisions/0016-hosting-on-free-tiers.md#platforms)).
