# Security and privacy rules

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-10-24

Strict rules for protecting data and keys, especially when calling LLM providers (FR-08). All data in this project is simulated, but it is handled exactly as real data would be, so the habits and the controls are right from the start.

## Principles

1. **Minimize.** Collect, keep, send, and show only what a task needs.
2. **Deny by default.** No access without an explicit rule.
3. **Least privilege** for every role, key, and component.
4. **Defense in depth.** No single control is trusted alone.
5. **Distrust content.** Every message and document is untrusted input.

## Data classification

**SEC-01.** Every piece of data belongs to exactly one class, and each class has fixed handling:

| Class | Examples | Stored in | Logs and telemetry | Sent to an LLM provider | Shown in the UI |
|---|---|---|---|---|---|
| Public | KB policy documents, project docs | Anywhere | Yes | Yes | Yes |
| Internal | IDs, versions, statuses, reason codes, metrics, settings without secrets | Component stores, telemetry | Yes | No (not needed) | To staff and developers |
| Confidential | Customer messages, drafts, replies, staff notes, order, shipment, and refund details, customer profile (name, email, phone, address), staff identity | `backend` database; `ai-service` processes it only in memory | Never | Only the allow-listed, masked subset ([below](#data-sent-to-llm-providers)) | Only to roles that need it |
| Secret | API keys, credentials, session tokens, signing keys | Secret settings only | Never | Never | Never |

**SEC-02.** Simulated data is classified as if it were real.

**SEC-03.** Every new field in a contract or a data store states its class in its description. A field without a class is treated as Confidential.

## Data sent to LLM providers

**SEC-04.** `ai-service` sends an LLM provider only:

1. the customer's message text, after masking;
2. snippets of retrieved KB documents;
3. allow-listed order context fields.

Everything else is forbidden, including names, emails, phone numbers, addresses, payment data, staff identity, internal IDs, and other tickets.

**SEC-05.** The order context allow-list (for example order status, shipment status, refund status, relevant dates, amounts) is defined in the `ai-service` contract. `backend` sends only allow-listed fields, and `ai-service` puts into a prompt only the fields that prompt needs.

**SEC-06.** Before every LLM call, personal-data patterns in text are replaced by typed placeholders: `[EMAIL]`, `[PHONE]`, `[CARD]`, `[ADDRESS]`. Each pattern has tests with positive and negative examples.

**SEC-07.** The LLM provider and plan are chosen so that API data is not used for training and is retained as briefly as the provider allows. The LLM provider ADR records the terms that were checked.

**SEC-08.** Only `ai-service` calls LLM providers, over TLS, with a key used for nothing else.

## Secrets

**SEC-09.** Secrets never appear in the repository, logs, telemetry, URLs, error messages, test fixtures, container images, or the frontend bundle.

**SEC-10.** Secrets come from environment variables loaded into secret-typed settings (`SecretStr`). `.env` is git-ignored. `.env.example` contains placeholders only.

**SEC-11.** gitleaks runs in pre-commit and CI. A detected secret blocks the commit and the merge.

**SEC-12.** A secret that was ever committed or exposed is rotated immediately, even if the commit was reverted ([Incidents](#incidents)).

**SEC-13.** Each environment and each component has its own keys, with the narrowest scope the provider allows.

## Authentication and authorization

**SEC-14.** `backend` authenticates every request except the public operations listed in the contract (health checks).

**SEC-15.** Roles are at least `customer` (shop demo persona), `staff`, and `supervisor` (authority for FR-06 actions). The permission matrix is defined in the backend contract.

**SEC-16.** Authorization is deny by default. Every operation declares its required role in the contract, and `backend` checks it in the application layer, not only in middleware.

**SEC-17.** Object-level access is checked on every request: a customer reaches only their own orders and tickets, and staff reach only tickets they are allowed to handle. An ID in a URL is never proof of access.

**SEC-18.** Actions that require authority (refund decisions, transaction disputes, policy exceptions) are allowed only for the authorized role (FR-06). The check is in `backend` and is covered by guardrail tests ([TEST-26](testing.md#guardrail-tests)).

**SEC-19.** Session tokens are never stored in `localStorage` or `sessionStorage`. The session mechanism is defined in [ADR-0009](../decisions/0009-demo-accounts-and-cookie-sessions.md).

**SEC-20.** `frontend` hides actions a role cannot perform as a convenience only. `backend` is the only enforcement point.

## Input and output handling

**SEC-21.** All input is validated at each component boundary against the contract: types, lengths, and formats. Message text has one maximum length, defined in the shared contract schema (`MessageText`), so every component enforces the same limit. Invalid input is rejected, never repaired.

**SEC-22.** The UI renders customer text, drafts, staff notes, and KB snippets as plain text. Rendering raw HTML or unescaped Markdown is forbidden.

**SEC-23.** CORS allows only the `frontend` origin. The `frontend` sends a Content Security Policy that blocks inline scripts and unknown origins.

## Prompt injection

**SEC-24.** Customer messages and KB content are untrusted data. Prompts separate system instructions from data with explicit delimiters, and the instructions state that delimited content is data, not instructions.

**SEC-25.** The LLM has no tools and cannot act. Its output is text validated against a schema. Output is never executed, never fetched as a URL, and never selects a code path except through validated fields.

**SEC-26.** Instructions inside a message or a document never change routing, permissions, or what data is sent.

**SEC-27.** The evaluation set includes prompt-injection cases, both in customer messages and in documents. Each must end in safe behavior.

## Transport and runtime

**SEC-28.** Outside local development, all traffic uses TLS. In local development, components talk over the Docker Compose network, and only the `frontend`, `backend`, and observability UI ports are published to the host.

**SEC-29.** Containers run as non-root users. Images contain no secrets and no development credentials.

## Dependencies

**SEC-30.** Lockfiles pin every dependency. Vulnerability audits run in CI ([WF-31](workflow.md#dependencies)).

**SEC-31.** Dependencies come only from the official registries (PyPI and npm). Installing from URLs or git branches requires an ADR.

## Retention and exports

**SEC-32.** `backend` keeps tickets, suggestion snapshots, and decisions for evaluation. A reset script restores the simulated data to a known state.

**SEC-33.** Evaluation exports contain only the fields the evaluation needs, are written to git-ignored folders, and are never uploaded to any external service, except text sent to the approved LLM provider under SEC-04.

## Incidents

**SEC-34.** When a secret or Confidential data is exposed (committed, logged, or sent where it should not go), the person who notices it, on the same day: stops the exposure, rotates or purges, opens an issue labeled `security`, and adds a test or rule that prevents a recurrence.

## Security review

**SEC-35.** PRs that touch authentication, authorization, data classification, prompts, LLM calls, or telemetry redaction need two approvals ([WF-15](workflow.md#reviews)).
