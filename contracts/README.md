# Contracts

This folder holds the API and data contracts between `frontend`, `backend`, and `ai-service`, with their examples, their changelog, and the tooling that checks them and serves them as mocks. Contracts are the only shared truth between components ([ADR-0001](../docs/decisions/0001-system-architecture.md)); the rules for writing and changing them are in [docs/rules/contracts.md](../docs/rules/contracts.md). The contracts gatekeeper approves every change here.

## Contents

| Path | Content |
|---|---|
| [`backend.openapi.yaml`](backend.openapi.yaml) | The `frontend` ↔ `backend` contract, version 1.2.0 |
| [`ai-service.openapi.yaml`](ai-service.openapi.yaml) | The `backend` ↔ `ai-service` contract, version 1.0.0 |
| [`schemas/`](schemas/) | JSON Schemas shared by the OpenAPI files, one file per schema, named after its key in `components.schemas`, such as `Money.yaml` for `Money` ([CON-09](../docs/rules/contracts.md#openapi-style)). The same name in both places gives each shared schema exactly one name in the bundle and in generated code |
| [`examples/`](examples/) | One example file per outcome: `<operationId>/<outcome>.json`, and `problems/<outcome>.json` for the error responses that several operations share |
| [`CHANGELOG.md`](CHANGELOG.md) | Every contract change, with its version ([CON-24](../docs/rules/contracts.md#evolution)) |
| [`lint/supportiq-rules.ts`](lint/supportiq-rules.ts) | The custom lint rules |
| [`lint/fixtures/violations.openapi.yaml`](lint/fixtures/violations.openapi.yaml) | Test data that breaks each custom rule once. It is not a contract |
| [`scripts/check-lint-rules.ts`](scripts/check-lint-rules.ts) | The check that every custom rule reports its violation in the fixture |
| [`scripts/check-mock.ts`](scripts/check-mock.ts) | The check of the sign-in flow, the service token, the closed request body, and the example files through the Prism mock of each contract |
| `redocly.yaml` | The lint configuration |
| `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` | The pinned tooling, the lodash override, and the audit exception ([Tools](#tools)) |
| `tsconfig.json`, `eslint.config.js`, `.prettierrc.json` | Type checking, linting, and formatting of the TypeScript files |

The KB data contract comes in contract PR 3 ([contracts v1 design, Rollout](../docs/design/contracts-v1.md#rollout)).

## Set up

1. Install the Node.js version in [`../.nvmrc`](../.nvmrc), for example with `nvm install` in the repository root.
2. Enable the pnpm version pinned in `packageManager`. Node.js 24 includes Corepack:

   ```bash
   corepack enable pnpm
   ```

3. Install the tools from the lockfile, in this folder:

   ```bash
   pnpm install --frozen-lockfile
   ```

## Commands

Run every command in this folder.

| Command | What it does |
|---|---|
| `pnpm run check` | Type-checks, lints (ESLint), and checks the formatting (Prettier) of the TypeScript files; lints the contracts and validates every example file; then checks that every custom rule still reports its violation in the fixture. The `contracts-check` hook of pre-commit runs this command, locally and in CI |
| `pnpm run lint` | Lints the contracts and validates every example file against its schema ([Machine-checked rules](#machine-checked-rules)) |
| `pnpm run format` | Formats the TypeScript and JavaScript files with Prettier |
| `pnpm run check:mock` | Starts the Prism mock of each contract in turn and checks it. On port 4011, the `backend` mock: `createSession` sets the `supportiq_session` cookie, and `getCurrentSession` answers `401` without it and `200` with it. On port 4013, the `ai-service` mock: `createDraft` answers `401` without a bearer token, `200` with one, and `422` to an `order_context` field outside the allow-list. For both, the mock serves the `value` of an example file unchanged. CI runs this command |
| `pnpm run bundle` | Writes each contract as one file, with every `$ref` resolved, to `dist/backend.openapi.yaml` and `dist/ai-service.openapi.yaml`. `dist/` is not committed |
| `pnpm run mock` | Serves the `backend` contract as a mock at `http://127.0.0.1:4010` ([For consumers](#for-consumers)) |
| `pnpm run mock:ai-service` | Serves the `ai-service` contract as a mock at `http://127.0.0.1:4012` ([The `ai-service` mock](#the-ai-service-mock)) |

## Tools

| Tool | Version | License | Why it is needed |
|---|---|---|---|
| Node.js | 24.22.2, in `../.nvmrc`. Maintenance LTS; end of life on 2028-04-30 | MIT | Runs every tool below. Prism needs it ([ADR-0003](../docs/decisions/0003-tech-stack.md)). Version 24 includes Corepack, which installs the pinned pnpm |
| pnpm | 12.16.1, in `packageManager` | MIT | The package manager of [ADR-0003](../docs/decisions/0003-tech-stack.md) and [TS-01](../docs/rules/typescript.md#toolchain); installs exactly what `pnpm-lock.yaml` records |
| `@redocly/cli` | 2.72.1 | MIT | One tool for linting, the custom rules, example validation, and bundling. Its built-in rules cover the OpenAPI structure; its plugin interface runs the custom rules |
| `@stoplight/prism-cli` | 5.16.0 | Apache-2.0 | The mock server of [ADR-0003](../docs/decisions/0003-tech-stack.md). It serves the same example files that the validation checks |
| `typescript` | 6.0.3 | Apache-2.0 | Type-checks the custom rules and the scripts ([ADR-0003](../docs/decisions/0003-tech-stack.md)). Node.js runs the `.ts` files directly, without a build step. Version 6.0 is the newest that `typescript-eslint` supports |
| `@types/node` | 24.19.2 | MIT | The Node.js types that the rules and scripts use |
| `eslint` | 10.14.0 | MIT | Lints the TypeScript files and enforces the MUST limits of [CODE-11](../docs/rules/code.md) ([ADR-0003](../docs/decisions/0003-tech-stack.md), RULE-03) |
| `typescript-eslint` | 8.72.1 | MIT | The type-checked ESLint rule sets that [TS-02](../docs/rules/typescript.md#toolchain) requires |
| `prettier` | 3.9.10 | MIT | Formats the TypeScript files with `printWidth: 100` ([ADR-0003](../docs/decisions/0003-tech-stack.md), TS-02) |

- Redocly CLI telemetry is turned off in `redocly.yaml`, so no project data leaves the machine ([SEC-01](../docs/rules/security-and-privacy.md#data-classification)).
- Prism depends on `@scarf/scarf`, an install-time analytics package. `pnpm-workspace.yaml` forbids its install script, so it never sends anything.
- CI runs `pnpm audit --audit-level=high` ([WF-31](../docs/rules/workflow.md#dependencies)). `pnpm-workspace.yaml` overrides the lodash of `postman-collection` to 4.18.1, which fixes GHSA-r5fr-rjxr-66jc and GHSA-xxjr-mmjv-4gpg.
- `pnpm-workspace.yaml` also accepts one high advisory, GHSA-qxc2-j82w-r537 in `@faker-js/faker` 5.5.3, which Prism pulls through `postman-collection`. The fixed version, 10.5.0, breaks `postman-collection`. Prism mocks only this repository's own contract, so no untrusted template reaches faker. The exception is removed when Prism no longer pulls a vulnerable faker.

## Machine-checked rules

`pnpm run lint` checks every contract rule that a tool can check ([RULE-03](../docs/rules/README.md#enforcement)). It extends the Redocly `recommended-strict` rule set and adds these rules:

| Rule | Checked by |
|---|---|
| Unique `operationId` in camelCase ([CON-04](../docs/rules/contracts.md#openapi-style)) | `operation-operationId-unique`, `supportiq/operation-id-camel-case` |
| A summary and a description on every operation (CON-04) | `supportiq/operation-documented` |
| An explicit security requirement on every operation (CON-04), and the roles of every operation that needs a session in `x-supportiq-roles` ([SEC-16](../docs/rules/security-and-privacy.md#authentication-and-authorization)) | `security-defined`, `supportiq/operation-security` |
| A `4xx` response on every operation, except one that needs no session and takes no input other than `traceparent`, such as a health check (CON-06, [ERR-18](../docs/rules/errors-and-reliability.md#startup-and-health)) | `supportiq/operation-4xx-response`, which replaces the built-in `operation-4xx-response` |
| A description on every schema, property, parameter, and header, with its data class ([CON-05](../docs/rules/contracts.md#openapi-style), [SEC-03](../docs/rules/security-and-privacy.md#data-classification)) | `supportiq/schema-description` |
| `additionalProperties: false` on request bodies and the objects inside them ([CON-07](../docs/rules/contracts.md#openapi-style)) | `supportiq/request-body-closed` |
| snake_case properties and query or path parameters, and the prefixes and suffixes of the naming table, with `as_of` as the one timestamp without `_at` ([CON-18](../docs/rules/contracts.md#naming)) | `supportiq/property-naming`, `paths-kebab-case` |
| Problem types of the form `urn:supportiq:problem:<kebab-case-name>` ([CON-12](../docs/rules/contracts.md#api-conventions)) | `supportiq/problem-type-urn` |
| A `maximum` on every `limit` ([CON-14](../docs/rules/contracts.md#api-conventions)) | `supportiq/limit-maximum` |
| At least one example file for each response with a body, at the path that its operation or the shared folder fixes, and no unused file in an operation's folder ([CON-06](../docs/rules/contracts.md#openapi-style)) | `supportiq/response-examples` |
| Every example matches its schema, with no field that the schema lacks (CON-06, [CON-21](../docs/rules/contracts.md#evolution)) | `no-invalid-media-type-examples` |
| No unused component, and no unresolved `$ref` | `no-unused-components`, `no-unresolved-refs` |

A response without a body, such as `204`, has no example file. No problem is ignored. `scripts/check-lint-rules.ts` keeps the custom rules honest: `pnpm run check` fails when any of them stops reporting its violation in `lint/fixtures/violations.openapi.yaml`.

`supportiq/response-examples` looks for unused files only in the folders of the operations in the linted contract. It does not look in `examples/problems/`, because a later contract can share that folder and each contract is linted alone.

## How the examples are linked

Every entry in a response's `examples` map is a `$ref` to one file:

```yaml
examples:
  in-transit:
    $ref: ./examples/getShopOrder/in-transit.json
```

Each file is an OpenAPI Example Object: a `summary`, an optional `description`, and the body in `value`. Prism resolves the `$ref` and serves `value`. The example validation of `pnpm run lint` reads the same file and checks `value` against the response schema. The name of an example is the file name without `.json`.

## For consumers

The `backend` and `frontend` work streams build against these files in parallel. Never edit `contracts/` from a component change: a contract change goes through the [contract-first process](../docs/rules/contracts.md#contract-first-process).

### Generated code

| Side | Generator ([ADR-0003](../docs/decisions/0003-tech-stack.md)) | Output | Input |
|---|---|---|---|
| `frontend` | `openapi-typescript` for the types and `openapi-fetch` for the client | `frontend/src/api/generated/` ([TS-05](../docs/rules/typescript.md#project-layout), [TS-27](../docs/rules/typescript.md#api-access)) | `contracts/backend.openapi.yaml` |
| `backend` | `datamodel-code-generator` for the Pydantic request and response models | `backend/src/supportiq_backend/generated/__init__.py` ([PY-35](../docs/rules/python.md#fastapi)) | `contracts/backend.openapi.yaml` |

- Each component pins its generator in its own lockfile and documents the generation command in its README.
- Both generators read the contract directly and follow its relative `$ref`s. On 2026-11-05, `openapi-typescript` 7.10.1 and `datamodel-code-generator` 0.35.0 both generated code from `backend.openapi.yaml` and from the output of `pnpm run bundle`. From the source file, `openapi-typescript` warns that example names repeat across operations; the warnings do not change the generated types, and the bundle gives none. A tool that cannot follow relative `$ref`s reads the bundle. `backend` now pins `datamodel-code-generator` 0.90.0 in its lockfile.
- On 2026-11-12, `datamodel-code-generator` 0.90.0 also generated models from `ai-service.openapi.yaml`, for the `ai-service` client of `backend`. It ignores `not`: the generated `AiServiceReasonCode` keeps the two codes that only `backend` sets, and `NoDraftOutcome` accepts a `draft`. These two rules are therefore checked by the example validation, the mock, and the provider tests of `ai-service`, not by the generated types.
- Generated files live only in folders named `generated/`. They are never edited by hand and are excluded from linters and coverage. CI regenerates them and fails when the committed output differs ([CON-25, CON-26](../docs/rules/contracts.md#generated-code)).

### The mock

Run `pnpm run mock` in this folder. Prism serves the `backend` contract at `http://127.0.0.1:4010`, validates every request against it, and answers with the example files.

- During `frontend` development, proxy `/v1/` from the Vite dev server to `http://127.0.0.1:4010`, so the session cookie stays on the same origin as the page.
- Sign-in works as in `backend`: `createSession` answers `201` with `Set-Cookie: supportiq_session=EXAMPLE-NOT-A-SESSION-ID; …`. An operation that needs a session answers `401` without the cookie and its success example with it. Prism checks only that the cookie is present, not its value.
- A request that breaks the contract (an unknown field, a missing `Idempotency-Key`, `limit=101`) gets `422` with the first `422` example of the operation.
- Prism does not validate everything. A body that is not valid JSON gets no answer, so the request waits for the client's timeout. An empty `cursor=` and an empty `order_id=` get `200`. `backend` answers `422` to all three, so test those cases with `Prefer: code=422`.
- The mock is stateless: a ticket created with `createShopTicket` does not appear in `listShopTickets`, and the `Origin` check, the roles, and idempotency are not simulated.

Choose the outcome of a request with the `Prefer` header:

| You want | Send |
|---|---|
| The first success example | No `Prefer` header |
| Another success example | `Prefer: example=<name>`, for example `Prefer: example=manager` on `getCurrentSession` |
| An error outcome | `Prefer: code=<status>`, for example `Prefer: code=404` |
| One error example among several | `Prefer: code=<status>, example=<name>`, for example `Prefer: code=403, example=forbidden-origin` or `Prefer: code=422, example=last-active-manager` |

The example names of each response are the file names in its folder: `examples/<operationId>/` for success outcomes, and `examples/problems/` for the error outcomes. The `examples` map of each response in the contract lists them.

### The `ai-service` mock

Run `pnpm run mock:ai-service` in this folder. Prism serves the `ai-service` contract at `http://127.0.0.1:4012`, so `backend` can call it during development with `ai_service_base_url` set to that address.

- Every operation except the health checks needs `Authorization: Bearer <token>` and answers `401` without it. Prism checks only that a bearer token is present, not its value.
- A body that breaks the contract, such as an unknown field or an `order_context` field outside the allow-list, gets `422` with the first `422` example of the operation.
- The mock does not run the pipeline: it answers every valid request with the chosen example, whatever the message says. Choose the outcome with the `Prefer` header as above, for example `Prefer: example=llm-unavailable` on `createDraft`, `Prefer: example=staff-intent` on `createAnalysis`, or `Prefer: code=422, example=unknown-kb-version`.

### Example files as test fixtures

Cross-component tests use these files, never hand-written imitations of `backend` or `ai-service` ([TEST-11](../docs/rules/testing.md#test-doubles)).

- A test fixture reads the `value` of an example file. `summary` and `description` are documentation only.
- `frontend` component and feature tests answer a mocked request with the `value` of the example for that outcome, so every state of a screen is tested against a body that the contract validates.
- `backend` tests of its `ai-service` client answer each call with the `value` of the example for that outcome, so every draft status, every reason code, and every problem is handled against a body that the contract validates ([CON-28](../docs/rules/contracts.md#contract-tests)).
- `backend` provider tests run Schemathesis against every operation ([CON-27](../docs/rules/contracts.md#contract-tests)). State-changing requests need an `Origin` header from `allowed_origins`, and protected operations need the cookie of a seeded account. Provider tests may use example values as request data or expected shapes.
- Tests never change the example files. An outcome that no example covers is added here first, through a contract change.
