# Contract rules

> **Status:** Active · **Owner:** contracts gatekeeper · **Last reviewed:** 2026-11-05

Contracts are the only shared truth between components. This file defines how contracts change, how they are written, and the conventions every API follows. The reasons are in [ADR-0001](../decisions/0001-system-architecture.md) and [ADR-0004](../decisions/0004-api-conventions.md).

## Contract-first process

**CON-01.** Every change that touches a component boundary follows these steps in order:

1. Change `contracts/`: schema, examples, and a changelog entry.
2. Regenerate mocks and update contract tests.
3. Change the provider (`backend` or `ai-service`).
4. Change the consumer (`frontend` or `backend`).
5. Run contract tests on both sides. Merge only when both pass.

**CON-02.** Code MUST NOT change first with the contract "to follow later". An implementation that differs from its contract is a bug in the implementation.

## Layout

```text
contracts/
├── backend.openapi.yaml      # frontend ↔ backend
├── ai-service.openapi.yaml   # backend ↔ ai-service
├── schemas/                  # JSON Schemas referenced by the OpenAPI files
├── examples/
│   ├── <operation-id>/
│   │   └── <outcome>.json    # for example draft-ready.json, abstained.json
│   └── problems/
│       └── <outcome>.json    # error bodies of the responses that several operations share
├── kb-contract.md            # data contract for the knowledge base
├── CHANGELOG.md              # Keep a Changelog format
└── README.md                 # commands, tools, and how consumers use the files
```

An error response that several operations share, such as `401` or `503`, is defined once under `components.responses` (CON-09), so its examples live once in `examples/problems/` instead of being copied into every operation's folder. The example files are OpenAPI Example Objects, which hold the body in `value`. The checks and the tooling are described in [contracts/README.md](../../contracts/README.md).

## What every contract specifies

**CON-03.** Every contract states:

- **Schema:** fields, types, required or optional, value constraints (lengths, ranges, patterns).
- **Semantics:** the meaning and unit of every field, what `confidence` means, and what each status and reason code means.
- **Failure behavior:** what each failure returns (timeout, LLM error, no document, low confidence), so the caller always has defined behavior.
- **Timeouts:** the caller's timeout and the latency target, linked to the requirements.
- **Security:** the role required for each operation.
- **Compatibility:** which changes are additive and which are breaking.
- **Responsibility:** what the provider guarantees and what it never does. For example, `ai-service` never sends anything to a customer.

## OpenAPI style

**CON-04.** Contracts use OpenAPI 3.1. Every operation has a unique `operationId` in `camelCase`, a `summary`, a `description`, a security requirement, and responses for every outcome.

**CON-05.** Every schema and every property has a `description` that states meaning and unit. A property without a description fails review.

**CON-06.** Every operation has at least one example per outcome: success, each business outcome (abstained, escalation recommended, LLM unavailable), invalid request, and server error.

**CON-07.** Request bodies set `additionalProperties: false`, so providers reject unknown fields. Responses are read by tolerant consumers ([Evolution](#evolution)).

**CON-08.** Required fields are listed explicitly. A field is optional only when its absence has a defined meaning, which the description states. `null` is not used to signal errors or "unknown".

**CON-09.** Reusable types (`Citation`, `ReasonCode`, `IntentDistribution`, `ProblemDetails`) are defined once under `components.schemas` or `schemas/` and referenced, never copied.

## API conventions

**CON-10.** REST over HTTP with JSON. The major version is in the path: `/v1/...`.

**CON-11.** Business outcomes (draft ready, abstention, escalation recommended, LLM unavailable) return `200` with a `status` and `reason_codes`. HTTP error codes are only for technical failures:

| Status | Meaning |
|---|---|
| `200` | The operation completed; read `status` for the business outcome |
| `201` | A resource was created |
| `202` | The request was accepted and continues asynchronously; poll the returned resource |
| `204` | The operation completed and has no response body |
| `400`, `422` | The request is invalid |
| `401`, `403` | Not authenticated, or not allowed |
| `404` | The resource does not exist |
| `409` | Conflict, for example an idempotency key reused with a different body |
| `500` | Unexpected failure in the provider |
| `503` | The provider is not ready (for example, the model artifact is not loaded) |

**CON-12.** Error bodies use Problem Details ([RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)) with `type` values from a registry in the contract, in the form `urn:supportiq:problem:<kebab-case-name>`. Error bodies never include stack traces, internal names, or confidential data.

**CON-13.** Trace context travels in the W3C `traceparent` header ([ADR-0007](../decisions/0007-observability-stack.md)). Write operations that a client may retry take an `Idempotency-Key` header ([ERR-15](errors-and-reliability.md#idempotency)). Sign-in and sign-out take none and are never retried automatically: before sign-in there is no account to scope a key to, a repeated sign-in only creates one more session, and a repeated sign-out gets `401`, which the client treats as signed out. Custom `X-` headers are forbidden.

**CON-14.** Lists are paginated with a cursor: requests take `limit` and `cursor`; responses return `items` and `next_cursor`. Every list has a documented maximum `limit`.

**CON-15.** Identifiers are opaque strings. Consumers never parse or construct them.

**CON-16.** Money is an integer amount in minor units plus an ISO 4217 currency code (`amount_minor`, `currency`). Floating-point money is forbidden.

**CON-17.** Timestamps are RFC 3339 strings in UTC. Durations are integers in milliseconds with a `_ms` suffix.

### Naming

**CON-18.** Names follow this table:

| Item | Convention | Example |
|---|---|---|
| Paths | Plural nouns, kebab-case | `/v1/tickets`, `/v1/analyses` |
| Operation IDs | `camelCase` verb phrase | `createDraft` |
| JSON fields | `snake_case` | `kb_version` |
| Enum values | `lower_snake_case` | `draft_ready`, `low_confidence` |
| Timestamps | `_at` suffix | `created_at` |
| Durations | `_ms` suffix | `latency_ms` |
| Booleans | `is_`, `has_`, or `can_` prefix | `is_expired` |
| Identifiers | `_id` suffix | `ticket_id` |
| Counts | `_count` suffix | `citation_count` |
| Versions | `_version` suffix, string | `model_version` |

## Evolution

**CON-19.** Compatible changes: adding an optional request field, adding a response field, adding an endpoint, adding an enum value to a response (consumers handle unknown values per CON-22).

**CON-20.** Breaking changes: removing or renaming a field, changing a type or meaning, making an optional request field required, removing an enum value. A breaking change needs a new major version (`/v2`) and a migration plan in a design doc.

**CON-21.** Consumers MUST ignore unknown response fields (tolerant reader). Providers MUST NOT send fields that are not in the contract.

**CON-22.** Consumers MUST map unknown enum values to a safe default at the boundary. An unknown AI status means manual handling; an unknown reason code is shown as "unspecified reason".

**CON-23.** A deprecated field or endpoint is marked `deprecated: true`, documented in the changelog with its replacement, and kept for at least one milestone before removal.

**CON-24.** Every contract change bumps `info.version` (SemVer) and adds a `CHANGELOG.md` entry.

## Generated code

**CON-25.** Server models, client types, and mocks are generated from `contracts/`. Generated files are never edited by hand.

**CON-26.** Generated code lives in folders named `generated/`, excluded from linters and coverage. CI regenerates the code and fails if the committed output differs.

## Contract tests

**CON-27.** Provider tests: `backend` and `ai-service` return responses that validate against the schema for every outcome, including each error.

**CON-28.** Consumer tests: `frontend` and `backend` run against mocks generated from the contract and handle every status and reason code, including unknown ones.

**CON-29.** CI blocks the merge when contract tests fail or when an implementation drifts from its OpenAPI file.

## Contract review checklist

- [ ] Every new field has a description with meaning and unit.
- [ ] Every outcome, including failures, has an example.
- [ ] Names follow the naming table.
- [ ] The change is classified as compatible or breaking, and versioned accordingly.
- [ ] The changelog entry explains what changed and why.
- [ ] Security requirements are declared for new operations.
