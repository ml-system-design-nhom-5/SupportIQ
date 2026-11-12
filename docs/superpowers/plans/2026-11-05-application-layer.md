# Application layer implementation plan

> Implement inline with `executing-plans`. The user prohibits subagents. Existing approved designs are the specification; do not reopen their layout or stack decisions.

**Goal:** Build the shop, support console and admin application against a persistent, role-protected backend, runnable directly on Windows.

**Architecture:** Preserve existing ML/evaluation modules. Add `apps/backend` for application state and `/v1` operations, `apps/frontend` for the React application, and a stateless HTTP AI boundary. PostgreSQL stores accounts, sessions, tickets, jobs, snapshots, decisions and audit events. Native startup creates an isolated local PostgreSQL cluster using installed binaries; it never changes the machine's existing cluster.

**Spec:** `docs/design/backend-foundation.md`, `shop-ui.md`, `console-ui.md`, `admin-ui.md`, and `contracts-v1.md` (revision 2 remains in review).

## Global constraints

- Native Windows startup, no Docker dependency; no subagents.
- Import the existing mock orders without editing the source. Preserve source IDs and normalize documented enum differences. VND amounts are already in minor units.
- One human-approved reply per ticket; no commerce writes; no admin access to customers.
- Use the approved palette, typography and three-column console. The dealt framed-sheet style yields to the approved geometry. No invented policies, AI confidence or report totals.
- No confidential browser persistence or logs; keys and session IDs remain server-side.

## Review focus

- Cross-customer object access returns 404, and shop payloads never contain AI fields.
- Repeated writes reuse one result; changed bodies with the same key return 409.
- Authority remains set after intent correction, AI failure or retry.
- Concurrent sends, account changes and stale suggestions preserve state and sessions.
- Source orders contain inconsistent customer names for repeated customer IDs; ownership follows customer_id, never names.

## Tasks

- [x] Backend foundation: write API guardrail tests first; implement typed settings, migrations, role-limited database access, sessions, commerce import, audit and idempotency. Verify against an isolated PostgreSQL database.
- [x] Ticket workflow: test sending, proposal approval, escalation, warning acknowledgement, placeholder rejection and stale suggestions. Implement persistent suggestions and leased jobs with HTTP AI calls and manual fallback.
- [x] Frontend: scaffold the pinned stack; implement shared tokens, status components, accessible dialogs, session routing, shop, console, reports and admin. Verify type checking, component tests and production build.
- [x] Windows runtime: provide install/start/stop commands, generated local credentials, isolated PostgreSQL and same-origin serving. Verify actual startup and health.
- [x] Full flow: run customer → ticket → staff/manager → sent reply → customer, role isolation and admin session revocation tests. Inspect desktop, tablet and phone screenshots; record critique and checks.
- [x] Documentation: record actual design tokens and runtime commands, generated API contract, source-data mappings and remaining limits. Run existing tests and report failures accurately.

## Execution ledger

- Source designs are already Approved; implementation is authorized by the user's request. No new design-approval round is needed.
- Native PostgreSQL 18 binaries are available on this machine. Prefer an application-local cluster over changing the existing Windows service.
- `mock_orders.json` contains 100 orders and 15 orders for `demo-customer`; source IDs differ from the example seed formats in backend-foundation. Preserve them and detect both formats during pseudonymization.
- Independent review is replaced with an inline review because the user explicitly prohibits subagents.
