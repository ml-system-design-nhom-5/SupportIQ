# Changelog

All notable changes to the contracts in this folder. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and each contract is versioned with [Semantic Versioning](https://semver.org/spec/v2.0.0.html) in its `info.version` (CON-24).

## `backend.openapi.yaml`

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
