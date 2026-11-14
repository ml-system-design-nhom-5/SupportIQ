# Unified Staff + Admin Console Design & Implementation Plan

**Date:** 2026-11-14  
**Goal:** Remove the distinct Manager UI and unify `admin` and `staff` into one employee console (`/console`) with capability-gated admin views, preserving Customer `/shop`, existing auth/isolation/idempotency/audit guarantees, and legacy backend compatibility for persisted `manager` records.

## Architecture & Role Matrix

| Capability / Surface | `customer` | `staff` | `admin` | legacy `manager` (backend/session compat) |
|---|---|---|---|---|
| Landing route (`roleHome`) | `/shop` | `/console` | `/console` | `/console` |
| Customer Shop (`/shop/*`) | Allow | Redirect/Deny | Redirect/Deny | Redirect/Deny |
| Console Shell (`Brand: SupportIQ Console`) | Deny | Allow (`Tickets`) | Allow (`Tickets`, `Reports`, `Accounts`, `Versions`) | Allow (`Tickets`, `Reports`) |
| Ticket Inbox (`open`) & Workspace | Deny | Allow | Allow | Allow |
| Ticket Inbox (`awaiting_approval`, `escalated`, `closed`) | Deny | 403 Denied | Allow | Allow |
| `correct_intent`, `retry_suggestion`, `escalate` (on `open`) | Deny | Allow | Allow (`escalate` on `open`) | `correct_intent`/`retry` only |
| `submit_reply_proposal` (on `open`) | Deny | Allow | N/A (`admin` sends directly) | N/A |
| `send_reply` (routine, `not is_authority_required`) | Deny | Allow | Allow | Allow |
| `send_reply` (authority / escalated / awaiting approval) | Deny | 403 Denied | Allow | Allow |
| Self-approval guard (`basis="reply_proposal"` when proposer == actor) | N/A | 403 Denied | 403 Denied (`self-approval-forbidden`) | 403 Denied |
| Reports (`/console/reports`, `/v1/console/reports`) | Deny | 403 Denied | Allow | Allow |
| Accounts (`/console/accounts`, `/v1/admin/accounts*`) | Deny | 403 Denied | Allow (no self-edit, no `admin` role mutation, no new `manager` grants in UI) | 403 Denied |
| Versions (`/console/versions`, `/v1/admin/versions`) | Deny | 403 Denied | Allow | 403 Denied |
| Observability (`/v1/admin/observability/*`) | Deny | 403 Denied | Allow | Allow |
| Legacy `/admin/*` deep links | Redirect -> denied | Redirect -> denied | `/admin/accounts` -> `/console/accounts`, `/admin/versions` -> `/console/versions`, `/admin/*` -> `/console/accounts` | Redirect -> denied |

## Key Design Decisions

1. **Single Shell (`area: 'shop' | 'console'`)**: Remove the separate `area="admin"` shell and top nav split. `admin` lands on `/console` alongside `staff`, with admin-only navigation links (`Reports`, `Accounts`, `Versions`) rendered by role. Keep quiet light **Achromatic Ledger** palette (`#f8fafc` ground, `#ffffff` surface, `1px solid var(--border)`).
2. **Legacy `manager` Compatibility Without Product UI Exposure**:
   - Do **not** drop or rewrite persisted `manager` DB rows, `Account.role` data, PostgreSQL trigger `protect_account_role()`, or `RoleInput(role: Literal["staff", "manager"])` so existing tests (`test_application.py`, `test_backend_safety_closure.py`, `test_reports_correctness.py`, `test_full_pipeline.py`) and audit trails stay intact.
   - Remove Manager UI branding/prompts/role-grant options: `SignIn` lists `staff-1, admin-1, customer-1`; ticket banners/helpers say *"administrator"* / *"authorized reviewer"* instead of *"manager"*; `Accounts` never offers `"Make manager"` on `staff` rows (only `"Make staff"` on legacy `manager` rows to demote/migrate off legacy role, plus `Deactivate`/`Reactivate`).
3. **Self-Approval & Authorization Defense-in-Depth**:
   - Backend route allowlists (`apps/backend/main.py`) and service checks (`apps/backend/tickets/service.py`) both enforce permissions (`admin` gains `staff` `open`-ticket triage + existing `manager` authority/reports/approval; `staff` stays strictly limited to `open` tickets and forbidden from reports/accounts/versions/authority send).
   - Explicitly reject `basis="reply_proposal"` in `tickets/service.py` if `ticket.proposal.get("actor_account_id") == actor.account_id` (`403 self-approval-forbidden`), plus retain `accounts/service.py` self-modification block (`target.account_id == actor.account_id`).

## Implementation Plan

1. **Backend (`apps/backend/main.py`, `apps/backend/tickets/service.py`)**:
   - Define concise role tuple/list helpers for console, authority, and account-eligible roles.
   - Update console endpoints & `allowed_actions` / `act` to grant `admin` console/ticket/proposal-approval/escalation/report access, forbid `staff` escalation bypasses/authority replies/reports/admin, and enforce `self-approval-forbidden`.
   - Keep `accounts/service.py` untouched except verifying `403` / `422` behavior on admin/staff/manager boundaries.
2. **Frontend (`apps/frontend/src/{session.tsx,App.tsx,styles.css,components/ui.tsx,features/console.tsx,features/admin.tsx}`)**:
   - Update `roleHome.admin = '/console'`, unify `Shell`, add `/console/accounts` & `/console/versions` routes + `/admin/*` redirects, fix `Tickets` active nav logic.
   - Update `console.tsx` authority checks (`admin` or legacy `manager`) and remove `"manager"` copy.
   - Update `admin.tsx` (`Accounts` + `AssetVersions`) to render cleanly inside `.console-main` (`.admin-content` matching `.reports-content` layout) and remove `"Make manager"` UI grants.
3. **Tests & Verification**:
   - Add `tests/application/test_unified_console_permissions.py` covering the full `admin`/`staff`/legacy `manager`/`customer` permission matrix & self-approval protection.
   - Extend `apps/frontend/src/features/console-permissions.test.tsx` for unified navigation, redirects, admin authority actions, staff denial, and no `"Make manager"` grant button.
   - Run Vitest, TypeScript check, Vite build, `impeccable detect --json`, Pytest suites, restart ONLY SupportIQ backend preserving Fit2 on `:8002`, and run real headless Playwright UI + screenshot verification.
