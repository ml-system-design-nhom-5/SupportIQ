# Security and privacy rules

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-11-12

Strict rules for protecting data and keys, especially when calling LLM providers (FR-08, FR-09). All data in this project is simulated, but it is handled exactly as real data would be, so the habits and the controls are right from the start.

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
| Confidential | Customer messages (raw or pseudonymized), drafts, replies, staff notes, order, shipment, and refund details, customer profile (name, email, phone, address), staff identity, the pseudonym map | `backend` database; `ai-service` processes pseudonymized text only in memory | Never | Only the allow-listed subset, pseudonymized by `backend` and masked by `ai-service` ([below](#data-sent-to-llm-providers)) | Only to roles that need it |
| Secret | API keys, credentials, session tokens, signing keys | Secret settings only | Never | Never | Never |

**SEC-02.** Simulated data is classified as if it were real.

**SEC-03.** Every new field in a contract or a data store states its class in its description. A field without a class is treated as Confidential.

## Data sent to LLM providers

**SEC-04.** `ai-service` sends an LLM provider only:

1. the customer's message text, as pseudonymized by `backend` ([SEC-36](#pseudonymization)) and then masked ([SEC-06](#data-sent-to-llm-providers));
2. snippets of retrieved KB documents;
3. allow-listed order context fields.

Everything else is forbidden, including names, emails, phone numbers, addresses, payment data, staff identity, internal IDs, and other tickets.

**SEC-05.** The order context allow-list (for example order status, shipment status, refund status, relevant dates, amounts) is defined in the `ai-service` contract. It contains no identifiers and no address. `backend` sends only allow-listed fields, and `ai-service` puts into a prompt only the fields that prompt needs.

**SEC-06.** Before every LLM call, `ai-service` replaces personal-data patterns that are still present outside placeholders with masks: `[EMAIL]`, `[PHONE]`, `[CARD]` ([ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md#placeholder-syntax)). Masking is the second layer and never replaces pseudonymization. Each pattern has unit tests with at least five positive and five negative examples. Every mask applied is logged as `personal_data.masked` at `warning`, with the type only, because it means pseudonymization missed a value.

**SEC-07.** The LLM provider and plan are chosen so that API data is not used for training and is retained as briefly as the provider allows. The LLM provider ADR records the terms that were checked.

**SEC-08.** Only `ai-service` calls LLM providers, over TLS, only to the hosts on the egress allow-list ([SEC-40](#transport-and-runtime)), with a key used for nothing else.

## Pseudonymization

The mechanism, the placeholder syntax, and the detectors are defined in [ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md).

**SEC-36.** `backend` MUST pseudonymize every customer message before any text derived from it leaves `backend`. `ai-service` MUST NOT receive raw personal data. If pseudonymization fails, nothing is sent: the suggestion parts become `unavailable` with `pseudonymization_failed` (fail closed). A detector can still miss a value; a miss is not a failure, and it is measured and reported against NFR-06 ([ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md#detection)).

**SEC-37.** The pseudonym map is stored only in the `backend` database and is Confidential. Only the `pseudonymization` feature module reads or writes it, through its public API, and an import-linter contract enforces this. Its rows are inserted once and never updated. Map rows are never returned by any operation, logged, or exported. Restoration happens only when `backend` builds AI text for `/console` or compares a sent reply with its draft. The original values behind pseudonyms MUST NOT appear in logs, telemetry, error messages, or exports. Responses may still contain the Confidential data that their schema defines, such as a customer's display name in the ticket workspace.

**SEC-38.** No placeholder reaches a customer. `backend` rejects every reply and reply proposal body that contains text matching the placeholder syntax, with `422 invalid-request`. Pseudonymized text is still Confidential: pseudonymization is not anonymization.

## Secrets

**SEC-09.** Secrets never appear in the repository, logs, telemetry, URLs, error messages, test fixtures, container images, or the frontend bundle.

**SEC-10.** Secrets come from environment variables loaded into secret-typed settings (`SecretStr`). `.env` is git-ignored. `.env.example` contains placeholders only.

**SEC-11.** gitleaks runs in pre-commit and CI. A detected secret blocks the commit and the merge.

**SEC-12.** A secret that was ever committed or exposed is rotated immediately, even if the commit was reverted ([Incidents](#incidents)).

**SEC-13.** Each environment and each component has its own keys, with the narrowest scope the provider allows.

## Authentication and authorization

**SEC-14.** `backend` authenticates every request except the public operations listed in the contract (health checks).

**SEC-15.** There are exactly four roles ([ADR-0012](../decisions/0012-roles-v1.md)): `customer` (shop demo persona), `staff` (Tier 1 support), `manager` (Tier 2 support, with authority for FR-06 actions and access to reports), and `admin` (accounts and versions only). The permission matrix is defined in the backend contract.

**SEC-16.** Authorization is deny by default. Every operation declares its required role in the contract, and `backend` checks it in the application layer, not only in middleware.

**SEC-17.** Object-level access is checked on every request: a customer reaches only their own orders and tickets, staff and managers reach an order only through a ticket of the same customer, and an admin reaches no ticket, message, order, report, or customer account. An ID in a URL is never proof of access.

**SEC-18.** Actions that require authority (refund decisions, transaction disputes, policy exceptions, legal claims, suspected fraud) are allowed only for `manager` (FR-06). `backend` enforces this on every ticket where authority is required, and guardrail tests cover it ([TEST-26](testing.md#guardrail-tests)). A ticket without an AI result carries no flag: it relies on staff judgment, and the console reminds staff to route such requests to a manager ([contracts v1 design](../design/contracts-v1.md#authority-rule-fr-06)).

**SEC-19.** Session tokens are never stored in `localStorage` or `sessionStorage`. The session mechanism is defined in [ADR-0009](../decisions/0009-demo-accounts-and-cookie-sessions.md).

**SEC-20.** `frontend` hides actions a role cannot perform as a convenience only. `backend` is the only enforcement point.

**SEC-41.** The `admin` role is limited to managing internal accounts (`staff`, `manager`, `admin`) and viewing versions. An admin never sees a customer account: customer accounts are never listed, and a request about one returns `404`. An admin cannot call any `/v1/shop/` or `/v1/console/` operation, cannot give any account the `admin` role, cannot change their own role or status, and cannot demote or deactivate the last active manager. An admin creates only `staff` and `manager` accounts and resets only their passwords, never an `admin` account's password and never their own through that operation. Admin account lists show display names, login names, roles, and statuses only ([ADR-0012](../decisions/0012-roles-v1.md), [ADR-0015](../decisions/0015-account-creation-and-password-changes.md)).

**SEC-42.** A role change or a deactivation deletes every session of the account in the same transaction, so the change applies to its next request. A change of the own password deletes every other session of the account, and a password reset every session of it, in the same transaction, unless the person who makes the change chooses to keep them. No permission or session is cached outside PostgreSQL ([ADR-0011](../decisions/0011-deployment-and-runtime-topology.md), [ADR-0015](../decisions/0015-account-creation-and-password-changes.md)).

## Input and output handling

**SEC-21.** All input is validated at each component boundary against the contract: types, lengths, and formats. Message text has one maximum length, defined in the shared contract schema (`MessageText`), and pseudonymized text has its own (`PseudonymizedText`), so every component enforces the same limits. Invalid input is rejected, never repaired.

**SEC-22.** The UI renders customer text, drafts, staff notes, and KB snippets as plain text. Rendering raw HTML or unescaped Markdown is forbidden.

**SEC-23.** CORS allows only the `frontend` origin. The `frontend` sends a Content Security Policy that blocks inline scripts and unknown origins.

## Prompt injection

**SEC-24.** Customer messages and KB content are untrusted data. Prompts separate system instructions from data with explicit delimiters, and the instructions state that delimited content is data, not instructions.

**SEC-25.** The LLM has no tools and cannot act. Its output is text validated against a schema. Output is never executed, never fetched as a URL, and never selects a code path except through validated fields.

**SEC-26.** Instructions inside a message or a document never change routing, permissions, or what data is sent.

**SEC-27.** The evaluation set includes prompt-injection cases, both in customer messages and in documents. Each must end in safe behavior.

## Transport and runtime

**SEC-28.** Outside local development, every connection that leaves a host uses TLS: from the browser to the ingress, from the ingress to `backend`, and from `backend` and `ai-service` to every host they call ([ADR-0011](../decisions/0011-deployment-and-runtime-topology.md#ingress), [ADR-0016](../decisions/0016-hosting-on-free-tiers.md)). Browsers reach the system only through the ingress.

**SEC-29.** Containers run as non-root users. Images contain no secrets and no development credentials.

**SEC-40.** Each component makes outbound connections only to the hosts that [ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md#egress-control) lists for it:

- `ai-service`: only the LLM provider hosts on the egress allow-list;
- `backend`: only its database, `ai-service`, and the telemetry destination in its settings. Its one-off commands connect only to its database.

[ADR-0016](../decisions/0016-hosting-on-free-tiers.md#outbound-connections) decides how each list is enforced. The allow-list is a versioned file, and changing it needs the security review of SEC-35.

## Dependencies

**SEC-30.** Lockfiles pin every dependency. Vulnerability audits run in CI ([WF-31](workflow.md#dependencies)).

**SEC-31.** Dependencies come only from the official registries (PyPI and npm). Installing from URLs or git branches requires an ADR.

## Retention and exports

**SEC-32.** `backend` keeps tickets, suggestion snapshots, decisions, audit log entries, and pseudonym maps for evaluation. A reset script restores the simulated data to a known state.

**SEC-33.** Evaluation exports contain only the fields the evaluation needs, are written to git-ignored folders, and are never uploaded to any external service, except text sent to the approved LLM provider under SEC-04. Message and AI text in exports is in pseudonymized form, and exports never contain the pseudonym map. Tickets that have no pseudonym map (manual mode, or failed pseudonymization) are exported without message text.

## Audit log

**SEC-39.** The audit log is insert-only. The database role that `backend` uses has no `UPDATE` or `DELETE` privilege on it, and a trigger rejects both. Each entry is written in the same transaction as the change it records and holds identifiers, statuses, reason codes, versions, and numbers only, never message or AI text. Only the reset script, running as the database owner, removes entries. The event types are listed in the [contracts v1 design](../design/contracts-v1.md#audit-log).

## Incidents

**SEC-34.** When a secret or Confidential data is exposed (committed, logged, or sent where it should not go), the person who notices it, on the same day: stops the exposure, rotates or purges, opens an issue labeled `security`, and adds a test or rule that prevents a recurrence.

## Security review

**SEC-35.** PRs that touch authentication, authorization, data classification, pseudonymization, the audit log, the egress allow-list, prompts, LLM calls, or telemetry redaction need two approvals ([WF-15](workflow.md#reviews)).
