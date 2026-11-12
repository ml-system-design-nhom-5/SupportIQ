# backend

`backend` is the SupportIQ component that owns sign-in, the read-only shop, the ticket workflow behind `/console`, internal accounts, the simulated commerce data, the pseudonym maps, and the audit log ([ADR-0001](../docs/decisions/0001-system-architecture.md)). It implements the [backend foundation design](../docs/design/backend-foundation.md), the [account management design](../docs/design/account-management.md), and the [backend ticket workflow design](../docs/design/backend-ticket-workflow.md) against [`contracts/backend.openapi.yaml`](../contracts/backend.openapi.yaml) 1.2.0, and it calls `ai-service` through [`contracts/ai-service.openapi.yaml`](../contracts/ai-service.openapi.yaml) 1.0.0. The ticket workflow lands in steps on the branch `build/ticket-workflow` ([design, Rollout](../docs/design/backend-ticket-workflow.md#rollout)): `listConsoleTickets`, `getConsoleTicket`, `recordTicketView`, `createSuggestion`, and `sendReply` are served; `createReplyProposal`, `createEscalation`, `getConsoleKbDocumentVersion`, `getConsoleReport`, `getAdminVersions`, the two one-off commands, and the named-entity detector of [ADR-0017](../docs/decisions/0017-named-entity-model-from-its-release-url.md) are not yet. Until they are, the provider contract tests fail on those operations.

## Run and test

Both commands run in `backend/`, after [Set up](#set-up).

```bash
uv run --env-file .env backend serve --host 127.0.0.1 --port 8000
```

```bash
uv run --env-file .env pytest
```

The tests need a running PostgreSQL 17 and the two URLs of `.env`. Each pytest worker creates, migrates, and drops its own database, so the tests never touch the `supportiq` database.

## Set up

These steps work from a fresh clone.

1. Install [uv](https://docs.astral.sh/uv/) 0.11.11 or later. It installs the Python version of [`../.python-version`](../.python-version).

2. Install PostgreSQL 17 and start it. The rest of this guide uses port 5433, because another PostgreSQL may use 5432. With Homebrew:

   ```bash
   brew install postgresql@17
   ```

   Then set `port = 5433` in `$(brew --prefix)/var/postgresql@17/postgresql.conf`, which the install created, and start the server:

   ```bash
   LC_ALL=en_US.UTF-8 "$(brew --prefix postgresql@17)/bin/pg_ctl" -D "$(brew --prefix)/var/postgresql@17" -l "$(brew --prefix)/var/log/postgresql@17.log" start
   ```

   `LC_ALL` avoids the macOS failure `postmaster became multithreaded during startup`.

3. Create the owner role and the database. Choose your own password. The owner needs `CREATEROLE` to create `supportiq_app` and `CREATEDB` because the tests create databases.

   ```bash
   "$(brew --prefix postgresql@17)/bin/psql" -p 5433 -d postgres -c "CREATE ROLE supportiq_owner LOGIN CREATEDB CREATEROLE PASSWORD 'replace-with-owner-password'"
   "$(brew --prefix postgresql@17)/bin/psql" -p 5433 -d postgres -c "CREATE DATABASE supportiq OWNER supportiq_owner"
   ```

4. Install the locked dependencies:

   ```bash
   uv sync --locked
   ```

5. Create your settings. `.env` is ignored by git, and its values never leave your machine. Replace every placeholder, and use the same owner password as in step 3. A `.env` made before the ticket workflow needs the two new required settings `AI_SERVICE_BASE_URL` and `AI_SERVICE_TOKEN` of `.env.example`; without them `backend` does not start.

   ```bash
   cp .env.example .env
   ```

6. Create `supportiq_app`, apply the migrations, and load the seed:

   ```bash
   uv run --env-file .env backend create-app-role
   uv run --env-file .env backend migrate
   uv run --env-file .env backend seed
   ```

Docker is not part of local development. CI builds the [`Dockerfile`](Dockerfile), and Render runs it in the demo deployment ([ADR-0016](../docs/decisions/0016-hosting-on-free-tiers.md)).

## Commands

Every subcommand validates the settings first. A missing or invalid setting stops it with exit status 2 and a `settings.invalid` line that names the setting ([ARCH-34](../docs/rules/architecture.md)). A one-off command that fails exits with status 1. `backend serve` ends with the status of uvicorn, such as 3 when the port is taken.

| Command | Runs as | What it does |
|---|---|---|
| `backend serve --host <host> --port <port>` | `supportiq_app` | Runs one replica |
| `backend create-app-role` | owner | Creates or updates `supportiq_app` with the password of `DATABASE_URL_APP`, from [`create_app_role.sql`](src/supportiq_backend/migrations/create_app_role.sql). It refuses a role that has `SUPERUSER`, `REPLICATION`, or `BYPASSRLS` |
| `backend migrate` | owner | Applies every migration |
| `backend seed` | owner | Loads [`seed/synthetic-dev-only-v1.json`](seed/synthetic-dev-only-v1.json) into an empty database. It fails on a seeded database and changes nothing |
| `backend reset` | owner | Empties every backend table and seeds again in one transaction. It asks first; `--yes` skips the question |

Run the seed and reset commands in `backend/`, because the path of the seed file is relative to the working directory.

| Check | Command |
|---|---|
| Format | `uv run ruff format --check .` |
| Lint | `uv run ruff check .` |
| Types | `uv run pyright` |
| Layer and feature boundaries | `uv run lint-imports` |
| Unit tests only | `uv run pytest tests/unit` |
| Coverage | `uv run --env-file .env pytest --cov --cov-report=`, then the two reports below |

```bash
uv run coverage report --fail-under=80
uv run coverage report --fail-under=90 --include="*/supportiq_backend/*/domain/*,*/supportiq_backend/*/application/*"
```

## Demo accounts

`backend seed` creates these accounts ([ADR-0009](../docs/decisions/0009-demo-accounts-and-cookie-sessions.md)). Each person chooses the passwords in their own `.env`, one per role: `SEED_PASSWORD_CUSTOMER`, `SEED_PASSWORD_STAFF`, `SEED_PASSWORD_MANAGER`, and `SEED_PASSWORD_ADMIN`. Passwords are never written in the repository.

Every account can then change its own password, and an admin can create `staff` and `manager` accounts, with login names such as `staff-3`, and reset their passwords ([ADR-0015](../docs/decisions/0015-account-creation-and-password-changes.md)). Admin and customer accounts come only from the seed. `backend reset` restores the seeded accounts and passwords.

| Login name | Role |
|---|---|
| `customer-1`, `customer-2`, `customer-3` | `customer` |
| `staff-1`, `staff-2` | `staff` |
| `manager-1`, `manager-2` | `manager` |
| `admin-1`, `admin-2` | `admin` |

All seed data is simulated and labeled `synthetic-dev-only`.

## Layout

```text
backend/
├── src/supportiq_backend/
│   ├── platform/           # Clock, errors, events, settings, database, logging, tracing, web
│   ├── audit/              # The insert-only audit log
│   ├── idempotency/        # Records of retryable writes and the idempotency guard
│   ├── accounts/           # Sign-in, sessions, roles, internal accounts, and passwords
│   ├── commerce/           # The read-only catalog, orders, shipments, and refunds
│   ├── tickets/            # Tickets, messages, the console workflow, replies, and decisions
│   ├── suggestions/        # Suggestions, the job queue and its claim loop, the ai-service client
│   ├── pseudonymization/   # The detectors and the pseudonym map; only it reads the map (SEC-37)
│   ├── composition_root/   # The only place that wires everything: the command and the app
│   ├── migrations/         # Alembic migrations and the SQL script of supportiq_app
│   └── generated/          # Models generated from the backend contract; never edited by hand
├── seed/                   # The seed file
├── tests/
│   ├── unit/               # Domain and application, with fakes; the network is blocked
│   ├── integration/        # PostgreSQL, HTTP flows, and guardrails/, as supportiq_app
│   └── contract/           # Schemathesis, every documented outcome, and the role table
├── typings/                # Type stubs of the packages that ship none
├── Dockerfile
└── pyproject.toml          # Dependencies and the configuration of every tool
```

Each feature has the layers of [ARCH-16](../docs/rules/architecture.md):

| Layer | Holds | May use |
|---|---|---|
| `domain/` | Types, rules, errors, and ports as `Protocol` classes | The standard library, the public API of `platform` for the root error of [PY-20](../docs/rules/python.md) and for shared errors, types, and pure functions, and the public API of a feature below it for its identifiers and errors ([ARCH-11](../docs/rules/architecture.md)). No third-party package is reachable from it |
| `application/` | Use cases, which alone commit transactions (PY-41) | `domain/` and public APIs |
| `adapters/` | PostgreSQL and other implementations of the ports | `domain/` of the feature, and public APIs |
| `api/` | Routes and the mapping between contract models and domain types | `application/`, `domain/`, and `generated/` |

Features depend on each other in one direction, `tickets`, `suggestions`, `pseudonymization`, `commerce`, `accounts`, then `audit` and `idempotency`, then `platform`, and only through the `__init__.py` of the feature, its public API (ARCH-17, ARCH-18). `suggestions` reads and links ticket rows through the ports `SuggestionTickets` and `TicketAuthority`, which an adapter of `tickets` implements. Only `pseudonymization` imports its own internals, and its public API offers exactly two functions to the others: `PseudonymizeMessage.pseudonymize` and `RestorePseudonyms.restore` (ADR-0010, item 6). The console's order view reuses the shop's order mapping of `commerce.api.shop`, the one import that the contracts ignore by name. `uv run lint-imports` enforces this with the contracts in [`pyproject.toml`](pyproject.toml). `platform` has two more public entry points: `platform.web` for the interface layers, and `platform.persistence` for the PostgreSQL adapters.

The generated models are written by two commands, one per contract, and CI fails when a committed file differs. The models of `ai-service` live in `suggestions/adapters/generated/`, because only the adapters of `suggestions` read them:

```bash
uv run datamodel-codegen
uv run datamodel-codegen --profile ai-service
```

## Database

- `backend serve` connects only as `supportiq_app`, which has `SELECT` on commerce data and no `UPDATE` or `DELETE` on the audit log or on customer messages ([design, Database roles and privileges](../docs/design/backend-foundation.md#database-roles-and-privileges)). It can insert `staff` and `manager` accounts and update password hashes, never delete an account, and a trigger refuses an `admin` account from every role but the owner ([migration `r0002`](../docs/design/account-management.md#migration-r0002)). The tests connect the same way, so they prove the privileges.
- To add a migration, add one file to [`migrations/versions/`](src/supportiq_backend/migrations/versions/) that follows `r0001_foundation_schema.py`: one schema change, raw SQL, the privileges of every new table, and a working downgrade (PY-40). `tests/integration/schema/test_migration.py` runs upgrade and downgrade.
- Every table of the backend is listed in [`migrations/tables.py`](src/supportiq_backend/migrations/tables.py), which `reset` empties.
- Migration `r0003` adds the tables of the ticket workflow ([design, Tables](../docs/design/backend-ticket-workflow.md#tables)). Triggers keep a final suggestion part and a stored request unchanged, and let `tickets.status` change only along the state machine. `supportiq_app` may only select and insert pseudonym maps, replies, proposals, escalations, and staff decisions.

## Suggestion jobs

Each replica runs one claim loop with `SUGGESTION_WORKERS_PER_REPLICA` slots, started and stopped by the lifespan of the app ([ADR-0011](../docs/decisions/0011-deployment-and-runtime-topology.md#suggestion-job-queue), ARCH-41). A use case that creates a suggestion wakes the loop of its replica after the commit; otherwise the loop polls every `SUGGESTION_QUEUE_POLL_MS`. A job pseudonymizes the message first, in its own transaction, and sends nothing when that fails (SEC-36); it then calls `createAnalysis` and `createDraft` in parallel, or only `createDraft` with an intent override, and stores each result only while its attempt and its suggestion are current (ERR-22). A job of a stopped replica is claimed again when its lease expires. The tests of the HTTP operations create the app with `BackgroundWork.NONE`, so no job runs behind their back.

## Events

Every log line is one JSON object on standard output, with the attributes of an allow-list. The catalog is [`platform/domain/events.py`](src/supportiq_backend/platform/domain/events.py) ([LOG-12](../docs/rules/logging-and-observability.md)).

| Event | When |
|---|---|
| `startup.completed`, `shutdown.started` | A replica starts or stops |
| `settings.loaded`, `settings.invalid` | The settings are read; `settings.invalid` names the settings, never a value |
| `request.completed` | Every request ends, with the route template, the method, the status, and the duration |
| `request.failed` | A request fails unexpectedly, with the error type |
| `database.call_failed` | A database call fails or a timeout fires, and the request answers `503` |
| `log.forwarded` | A library logs at `warning` or above; the message is redacted |
| `session.created`, `sign_in.failed`, `sign_in.throttled` | Sign-in outcomes, never with a login name |
| `permission.denied` | A role calls an operation that it may not use |
| `account.role_changed`, `account.status_changed` | An admin changes an internal account |
| `account.created`, `account.password_reset` | An admin creates a `staff` or `manager` account, or resets its password, with the target account and never a login name or a display name |
| `account.password_changed` | An account changes its own password, with whether its other sessions ended |
| `password_change.failed`, `password_change.throttled` | A password change refused because the current password was wrong, or because the login name reached the sign-in failure limit |
| `ticket.created` | A customer creates a ticket, with `ticket_id` |
| `ticket.viewed`, `ticket.manual_handling_started` | Staff open a ticket; the AI of a ticket could not run, with the reason code |
| `suggestion.requested`, `suggestion.superseded`, `suggestion.part_cancelled`, `suggestion.completed` | A suggestion is created, replaced by a newer one, has its running calls cancelled, or ends with its draft status |
| `suggestion_job.claimed`, `suggestion_job.lease_expired`, `suggestion_job.failed` | The claim loop claims a job, ends a job without attempts left, or logs a failure once and goes on |
| `pseudonymization.failed`, `pseudonymization.rejected` | Pseudonymization fails closed because of a defect, or because the text is over 4 000 characters (ADR-0010, Failure handling) |
| `pseudonym.restore_failed` | A pseudonym of stored AI text is missing from the map |
| `ai_service.called`, `ai_service.call_failed`, `ai_service.contract_violated` | A call to `ai-service` answers, times out or fails, or is refused with `4xx` or answered outside the contract |
| `intent.overridden`, `reply.sent`, `decision.recorded` | Staff choose an intent, send a reply, or record a decision about a draft |
| `command.failed` | A one-off command fails, with the error type |
| `database.migrated`, `database_role.applied` | A one-off database command succeeds |
| `seed.loaded`, `seed.reset`, `seed.reset_cancelled` | The seed and reset commands |

Every request has a trace with its database spans, and ticket creation has the span `create_ticket` with `ticket_id` ([LOG-20](../docs/rules/logging-and-observability.md), LOG-07). A suggestion job runs in the span `run_suggestion_job`, in the trace of the request that created its suggestion, whose trace ID the suggestion stores; inside it are `pseudonymize_message` with `pseudonym_count` and `call_ai_service` with `ai_service_operation`. `sendReply` has the spans `send_reply` and `save_decision`. A failure marks the span of its request or command with the status and an exception event (LOG-22). `TRACE_EXPORTER` chooses whether spans leave the process; before they do, every attribute outside an allow-list is dropped, an exception keeps only its type, and a status keeps only its code. A line that a library logs outside every span carries IDs of the process.

## Known limits

- Logs and metrics are not exported over OTLP (LOG-01, LOG-24, #2): logs go to standard output, only traces reach the exporter, and the metric `http.server.request.duration` does not exist yet. The design's Goals do not include them, and no collector exists until `deploy/`.
- Pseudonymization runs without the named-entity detector of ADR-0010, step 4, until ADR-0017 lands it, so unknown names and addresses that no other step finds reach `ai-service`. The design does not allow a replica to run without that detector: the branch is not merged before it lands.
- Eight `pyright: ignore` comments remain in `tests/contract/`, on calls into Schemathesis, whose public types leave generics unparametrized ([PY-13](../docs/rules/python.md), #3).

## Tests

| Layer | Folder | What it proves |
|---|---|---|
| Unit | `tests/unit/` | Domain and application logic with a fake for every port, and the property that no sequence of role and status changes leaves no active manager or admin |
| Integration | `tests/integration/` | Privileges and triggers, idempotency, account changes, creations, and password changes under concurrency, seed and reset, and each flow over HTTP |
| Guardrails | `tests/integration/guardrails/` | The cases of [TEST-26](../docs/rules/testing.md) that apply here. `tests/contract/test_operations.py` and `tests/contract/test_permissions.py` hold the others |
| Contract | `tests/contract/` | Schemathesis over every operation, one test for each documented status, and every operation against all four roles. `tests/contract/consumer/` reads every example of the `ai-service` contract through the client (CON-28) and needs no database |

Tests run in random order and in parallel. Time comes from a fake clock, and Hypothesis runs derandomized, so a run repeats exactly with the `--randomly-seed=<seed>` value that pytest prints. The contract tests read `../contracts/`, so they need the whole repository.

## Dependencies

Each direct dependency, with why it is here ([WF-27](../docs/rules/workflow.md#dependencies)). `uv.lock` pins every transitive dependency.

### Runtime

| Name | Version | License | Why |
|---|---|---|---|
| fastapi | 0.162.0 | MIT | The web framework ([ADR-0003](../docs/decisions/0003-tech-stack.md)) |
| httpx | 0.28.1 | BSD-3-Clause | The client of `ai-service`, created once at startup ([backend ticket workflow design](../docs/design/backend-ticket-workflow.md#the-ai-service-client)); the tests also use it over ASGI |
| pydantic | 2.14.3 | MIT | Contract models and validation (ADR-0003) |
| pydantic-core | 2.50.4 | MIT | `PydanticCustomError` in the validators of the settings, imported directly |
| pydantic-settings | 2.16.2 | MIT | Typed settings, validated at startup (ARCH-34, PY-43) |
| sqlalchemy (with the `asyncio` extra, which adds greenlet) | 2.0.57 | MIT | Persistence (ADR-0003). Not 2.1, which the OpenTelemetry instrumentation does not support yet |
| alembic | 1.20.1 | MIT | Migrations (ADR-0003) |
| asyncpg | 0.32.0 | Apache-2.0 | The async PostgreSQL driver of SQLAlchemy, with a permissive license (WF-30) |
| argon2-cffi | 25.1.0 | MIT | Argon2id password hashes ([ADR-0009](../docs/decisions/0009-demo-accounts-and-cookie-sessions.md), statement 3) |
| starlette | 1.10.0 | BSD-3-Clause | The ASGI types and routing classes under FastAPI, imported directly by the middleware and the exception handler |
| uvicorn | 0.54.0 | BSD-3-Clause | The ASGI server that runs a replica. The standard library has none |
| opentelemetry-api | 1.45.2 | Apache-2.0 | Tracing ([ADR-0007](../docs/decisions/0007-observability-stack.md)) |
| opentelemetry-sdk | 1.45.2 | Apache-2.0 | The tracer provider and span processors (ADR-0007) |
| opentelemetry-exporter-otlp-proto-http | 1.45.2 | Apache-2.0 | OTLP export of traces (ADR-0007) |
| opentelemetry-instrumentation-fastapi | 0.66b2 | Apache-2.0 | The server span of each request (ADR-0007) |
| opentelemetry-instrumentation-sqlalchemy | 0.66b2 | Apache-2.0 | The database spans of each request (ADR-0007) |

These runtime dependencies have a license outside the list of WF-30, and the project lead accepted them:

- `certifi` (MPL-2.0), through `requests`, which `opentelemetry-exporter-otlp-proto-http` needs.
- `cffi` (MIT-0), through `argon2-cffi-bindings`.
- `greenlet` (MIT AND PSF-2.0), through `sqlalchemy[asyncio]`.
- `typing_extensions` (PSF-2.0), through `pydantic` and other packages.

### Development

| Name | Version | License | Why |
|---|---|---|---|
| pytest | 9.2.0 | MIT | The test runner (ADR-0003) |
| pytest-xdist | 3.8.0 | MIT | Parallel runs (TEST-15) |
| pytest-randomly | 5.0.0 | MIT | Random order (TEST-15) |
| pytest-socket | 0.8.1 | MIT | Blocks the network in unit tests (TEST-16) |
| pytest-cov | 7.1.0 | MIT | Coverage from pytest (TEST-21) |
| coverage | 7.17.2 | Apache-2.0 | Branch coverage and its floors (TEST-21) |
| anyio | 4.16.0 | MIT | The pytest plugin of async tests |
| hypothesis | 6.170.15 | MPL-2.0 | Property-based tests (ADR-0003, TEST-13). Its license is outside the list of WF-30, and the project lead accepted it |
| schemathesis | 4.33.1 | MIT | Contract tests (ADR-0003, CON-27) |
| datamodel-code-generator | 0.90.0 | MIT | Generates the models from the contract (ADR-0003, CON-25) |
| ruff | 0.17.4 | MIT | Format and lint (ADR-0003) |
| pyright (with the `nodejs` extra) | 1.1.414 | MIT | Strict types (ADR-0003) |
| import-linter | 2.16 | BSD-2-Clause | Layer and feature boundaries (ADR-0003, ARCH-11) |
| pip-audit | 2.10.1 | Apache-2.0 | Dependency vulnerabilities ([rules](../docs/rules/README.md#enforcement)) |

These development dependencies have a license outside the list of WF-30, and the project lead accepted them:

- `defusedxml` (PSF-2.0), through `py-serializable`, which `pip-audit` needs.
- `hypothesis` (MPL-2.0), a direct dependency.
- `pathspec` (MPL-2.0), through `black`, which `datamodel-code-generator` needs.

The build backend is `uv_build`, from the same release as uv (MIT or Apache-2.0).
