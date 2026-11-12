# Changelog

All notable changes to the contracts in this folder. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and each contract is versioned with [Semantic Versioning](https://semver.org/spec/v2.0.0.html) in its `info.version` (CON-24).

## `backend.openapi.yaml`

### [1.2.0] - 2026-11-12

Adds the review console of staff and managers and the versions page of the admin area, the operations that the project lead approved on 2026-11-12 from the [contracts v1 design](../docs/design/contracts-v1.md#rollout), as the [backend ticket workflow design](../docs/design/backend-ticket-workflow.md) implements them. Every change is compatible (CON-19): new operations, new schemas, and new problem types in responses. Consumers regenerate their code and map the new problem types to a safe default (CON-22). The provider tests of `backend` run over every operation, so they pass again only with the implementation of these operations (CON-01, step 5).

#### Added

- `listConsoleTickets` (`GET /v1/console/tickets`), for `staff` (`open` only) and `manager`: one queue per `status`, waiting tickets oldest first and closed tickets newest first, with a message excerpt of at most 160 characters.
- `getConsoleTicket` (`GET /v1/console/tickets/{ticket_id}`): the ticket workspace with the order, the customer's other orders, the current suggestion with pseudonyms restored, the proposal, the escalation, the reply, and `allowed_actions`.
- `recordTicketView` (`POST /v1/console/tickets/{ticket_id}/views`): starts the handling clock, and starts a `kb_version_changed` or `retry` suggestion when the rules of the contracts v1 design call for one.
- `createSuggestion` (`POST /v1/console/tickets/{ticket_id}/suggestions`): an intent correction (ESC-01) or a retry, answered with `202` and a pending suggestion.
- `createReplyProposal`, `sendReply`, and `createEscalation`, with request bodies discriminated by `basis`. `sendReply` is the only operation that sends anything to a customer, and staff get `403 authority-required` on a ticket that requires authority (FR-04, FR-06).
- `getConsoleKbDocumentVersion` (`GET /v1/console/kb-documents/{document_id}/versions/{version}`): the full KB document version, read from `ai-service`. The contracts v1 design named it `getKbDocumentVersion`; the new name keeps its example folder apart from that of the `ai-service` contract.
- `getConsoleReport` (`GET /v1/console/reports`), for `manager`: the figures of FR-10 and the handling time of NFR-11 for a period.
- `getAdminVersions` (`GET /v1/admin/versions`), for `admin`: the build version of `backend` and the versions that `ai-service` serves, with `ai_service_status`.
- The problem types `authority-required` (`403`), `invalid-ticket-state`, `suggestion-pending`, and `suggestion-superseded` (`409`), after the existing values of `ProblemDetails.type`.
- References to the shared schemas `IntentLabel`, `ConfidenceBand`, `AiReasonCode`, `AiItemId`, `KbDocumentId`, `KbDocumentVersionTag`, `AssetVersions`, `KbDocumentCitation`, `OrderContextCitation`, `RankedDocument`, `Warning`, and `Placeholder`.
- An example file for every outcome of the new operations, and twelve shared problem examples.

#### Changed

- `info.description`: the console writes join the `Origin` check and the `Idempotency-Key` list, and the timeouts name the three operations that read from `ai-service`.
- The descriptions of `OrderStatus`, `ShipmentStatus`, and `RefundStatus` say "simulated" instead of naming the `synthetic-dev-only` label, which evaluation reports never use.

### [1.1.0] - 2026-11-11

Adds the own password change, account creation, and password resets that [ADR-0015](../docs/decisions/0015-account-creation-and-password-changes.md) decides, as the [account management design](../docs/design/account-management.md) specifies them. Every change is compatible (CON-19): new operations, a new response field, a narrower response length, and new enum values in responses. Consumers regenerate their code; an older consumer ignores `login_name` (CON-21) and maps the new problem type and the new `violated_rule` values to a safe default (CON-22).

#### Added

- `changeOwnPassword` (`POST /v1/sessions/current/password-changes`), callable by every role: replaces the caller's own password and, when `is_signed_out_elsewhere` is true, ends the other sessions of the account. A wrong current password counts as a sign-in failure and returns `422` with `current_password_incorrect`.
- `createAdminAccount` (`POST /v1/admin/accounts`), for `admin`: creates an active `staff` or `manager` account with the login name `<role>-<number>`, with the next free number or the optional `login_number`.
- `resetAccountPassword` (`POST /v1/admin/accounts/{account_id}/password-resets`), for `admin`: replaces the password of a `staff` or `manager` account and, when `is_signed_out_everywhere` is true, ends every session of it.
- The schemas `Password` (1 to 128 characters, the limits of sign-in, shared by every new password field), `ChangeOwnPasswordRequest`, `CreateAdminAccountRequest`, and `ResetAccountPasswordRequest`.
- The required field `login_name` of `AdminAccountView`, so the admin area shows the login name of every account.
- The problem type `login-name-taken` (`409`), with the shared response `IdempotencyKeyReusedOrLoginNameTaken`, and the `422` responses `InvalidPasswordChange` and `InvalidPasswordReset`.
- The `AccountChangeRule` values `admin_password_unresettable` and `current_password_incorrect`, after the existing values.
- Example files for every outcome of the new operations, and `login_name` in the examples of `listAdminAccounts`, `changeAccountRole`, and `changeAccountStatus`.

#### Changed

- `display_name` in `SessionView` and `AdminAccountView` has at most 100 characters. It narrows only what `backend` sends.
- The `Idempotency-Key` parameter: password fields are not compared, because no password is stored (the exception to ERR-15). The same key with a different password returns the original result.
- `info.description`: the `Origin` check, the `Idempotency-Key` list, the throttle delay, and the responsibility of `backend` for passwords. The `Unauthenticated` response names password changes and resets as a cause of a deleted session.

### [1.0.1] - 2026-11-08

Clarifies three points that version 1.0.0 left open or stated wrongly: an `Idempotency-Key` reused with different path parameters, the responses of the ingress, and the products of an order. Version 1.0.0 did not cover the first case: read literally, `changeAccountRole` and `changeAccountStatus` would return the result of the first account and leave the second unchanged. No field, status code, or problem type changes. Every consumer regenerates its code, because the descriptions change.

#### Changed

- The `Idempotency-Key` parameter, the `IdempotencyKeyReused` response, and the problem type `idempotency-key-reused` in `ProblemDetails`: the same key with different path parameters returns `409 idempotency-key-reused`, as the same key with a different body does.
- `examples/problems/idempotency-key-reused.json`: the summary and the detail now say "a different request".
- Errors, in `info.description`: the ingress answers `413` or `429` before `backend` sees a request, and `502` or `504` when `backend` is unreachable or a write in flight fails, as ADR-0011 states. Version 1.0.0 said that all four come before `backend` sees a request. After `502` or `504` the outcome of a write is unknown, and a retry with the same `Idempotency-Key` cannot repeat its effect (ERR-15).
- `ShopOrderView.lines`: a product appears at most once in an order. The examples already follow this.

### [1.0.0] - 2026-11-05

Contract PR 2. The first version of the `frontend` ↔ `backend` contract, for the operations that the project lead approved on 2026-11-05 ([contracts v1 design, Rollout](../docs/design/contracts-v1.md#rollout)). There is no earlier consumer, so the change has no compatibility impact.

#### Added

- Sessions: `createSession`, `getCurrentSession`, and `deleteCurrentSession`, with the `sessionCookie` security scheme and the `supportiq_session` cookie ([ADR-0009](../docs/decisions/0009-demo-accounts-and-cookie-sessions.md)).
- Shop: `listShopProducts`, `getShopProduct`, `listShopOrders`, `getShopOrder`, `createShopTicket`, `listShopTickets` with its optional `order_id` filter, and `getShopTicket` ([ADR-0013](../docs/decisions/0013-shop-demo-with-read-only-catalog.md)).
- Admin: `listAdminAccounts`, `changeAccountRole`, and `changeAccountStatus` ([ADR-0012](../docs/decisions/0012-roles-v1.md)).
- Health: `checkLiveness` (`GET /health/live`) and `checkReadiness` (`GET /health/ready`).
- Shared schemas in `schemas/`, one file per schema, named after its key in `components.schemas`: `MessageText`, `Money`, `Timestamp`, `ProblemDetails` with the problem types that this version uses, `OrderStatus`, `ShipmentStatus`, and `RefundStatus`.
- `AccountChangeProblemDetails`, the `422` body of `changeAccountRole` and `changeAccountStatus`: a `ProblemDetails` with the extension member `violated_rule` (`AccountChangeRule`), which says why a well-formed change was refused: the admin limits 3 to 5 of ADR-0012, or an unchanged value. The admin area uses it to explain a refusal.
- Reusable parameters (`traceparent`, `Idempotency-Key`, `limit`, `cursor`, and the path identifiers) and one shared response for each error outcome.
- The caller's timeout of 10 000 ms and the bounds of `backend`, under Timeouts.
- An example file for every outcome of every operation, in `examples/<operationId>/` and, for the shared error responses, in `examples/problems/`.
