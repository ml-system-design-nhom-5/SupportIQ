# Unified Staff + Admin Console Implementation & Verification Audit (Worker D)

**Date:** 2026-11-14  
**Branch:** `minh`  
**Workspace:** `F:/Năm 3/SD/project/SupportIQ`

## Scope & Minimal Architecture

- **Design Plan:** [2026-11-14-unified-staff-admin-console.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/superpowers/plans/2026-11-14-unified-staff-admin-console.md)
- Removed standalone Manager UI entry/branding (`admin` -> `/console` in `roleHome`, single `Shell` with `area: 'shop' | 'console'`, removed `manager-1` from SignIn demo note, removed `"Make manager"` grants in `Accounts`, removed `"manager"` instructions in ticket banners/modals).
- Unified `admin` and `staff` into `/console`:
  - `admin` inherits authority ticket handling (`awaiting_approval`, `escalated`, `closed` inbox filter, direct `send_reply`, proposal approval, `/console/reports`) + open-ticket triage (`correct_intent`, `retry_suggestion`, `escalate`) + admin routes (`/console/accounts`, `/console/versions`). Legacy `/admin/accounts`, `/admin/versions`, and `/admin/*` redirect to unified `/console/*`.
  - `staff` remains restricted to `status=open` tickets (`403` on non-`open`, `/v1/console/reports`, `/v1/admin/*`, and direct authority replies) with only the `Tickets` nav tab.
  - Preserved legacy backend compatibility for persisted `manager` accounts (`accounts/service.py`, `seed.py`, PostgreSQL trigger `protect_account_role()`, `tickets/service.py`) without product UI exposure, and allowed legacy `manager` -> `staff` migration (`Make staff`) in `Accounts`.
  - Added explicit `self-approval-forbidden` (`403`) check in `apps/backend/tickets/service.py` blocking `basis="reply_proposal"` when `ticket.proposal.get("actor_account_id") == actor.account_id`.
  - Fixed Role column width in `apps/frontend/src/styles.css` (`.account-table-head`, `.account-row`) after Playwright visual inspection caught clipping of `Manager (legacy)` status pill.

## Modified / Added Files

- [apps/backend/main.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/main.py)
- [apps/backend/tickets/service.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py)
- [apps/frontend/src/session.tsx](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/session.tsx)
- [apps/frontend/src/App.tsx](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/App.tsx)
- [apps/frontend/src/features/console.tsx](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx)
- [apps/frontend/src/features/admin.tsx](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/features/admin.tsx)
- [apps/frontend/src/components/ui.tsx](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/components/ui.tsx)
- [apps/frontend/src/styles.css](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/styles.css)
- [tests/application/test_application.py](file:///F:/Năm%203/SD/project/SupportIQ/tests/application/test_application.py)
- [tests/application/test_unified_console_permissions.py](file:///F:/Năm%203/SD/project/SupportIQ/tests/application/test_unified_console_permissions.py)
- [apps/frontend/src/features/unified-console.test.tsx](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/features/unified-console.test.tsx)
- [docs/superpowers/plans/2026-11-14-unified-staff-admin-console.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/superpowers/plans/2026-11-14-unified-staff-admin-console.md)

## Verification Results (Post-Final-Edit)

1. `impeccable detect --json apps/frontend/src/App.tsx apps/frontend/src/features/console.tsx apps/frontend/src/features/admin.tsx apps/frontend/src/styles.css apps/frontend/src/components/ui.tsx` -> `[]` (0 findings).
2. `pnpm --dir apps/frontend test` -> `6 passed (6)`, `27 passed (27)` tests (`unified-console.test.tsx`, `console-permissions.test.tsx`, `console.test.tsx`, `reports.test.tsx`, `support.test.tsx`, `reply-rules.test.ts`).
3. `pnpm --dir apps/frontend run typecheck` (`tsc -b`) -> exit 0.
4. `pnpm --dir apps/frontend run build` (`vite build`) -> built `dist/` cleanly in 466ms.
5. `.venv\Scripts\python.exe -m pytest tests/application/test_unified_console_permissions.py tests/application/test_application.py tests/application/test_backend_safety_closure.py tests/unit/test_reports_correctness.py -v` -> **38 passed in 29.94s**.
6. `.venv\Scripts\python.exe -m pytest tests/application/test_workflow_privacy.py tests/unit/test_retry_draft.py tests/unit/test_typed_fault_propagation_a.py tests/application/test_reports_pg.py -v` -> **16 passed in 20.96s**.
7. Real Playwright MCP verification against `http://127.0.0.1:8080` (with Fit2 AI service on `:8002`, `live_llm_requests_made=0`, zero paid LLM calls):
   - `admin-1`: lands on `/console`, displays `Tickets`, `Reports`, `Accounts`, `Versions`, status filter works (`TCK-1016` open, `TCK-1077` escalated), `Accounts` shows no `"Make manager"` button and unclipped `"Manager (legacy)"` badge with `"Make staff"`, `Versions` shows `fit2-supcon-energy-boundary-v1` / `Available`, `/admin/accounts` redirects to `/console/accounts`.
   - `staff-1`: lands on `/console` with only `Tickets`, no status dropdown; direct `fetch` to `/v1/console/tickets?status=escalated`, `/v1/console/reports`, `/v1/admin/accounts`, `/v1/admin/versions`, `/v1/admin/observability/metrics` all return `403`; `/console/accounts` renders `"Permission denied — This area is for administrator accounts."`.
   - `manager-1` (legacy compat): lands on `/console` with `Tickets` + `Reports` only; `/v1/console/reports -> 200`, `/v1/admin/accounts -> 403`.
   - `customer-1`: lands on `/shop` intact; `/v1/console/tickets -> 403`.
   - Screenshots & snapshots saved under `artifacts/browser/unified-staff-admin-d-20261114/`.
