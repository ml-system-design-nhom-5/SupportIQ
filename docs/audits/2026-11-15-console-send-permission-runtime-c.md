# Worker C Independent Verification: Frontend Console Send Permission (`2e965b0`) & Grouped Runtime Integration

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Commit Verified:** `2e965b01bacbe560ba1bb4e32672aa8689e19aa1` (`fix(frontend): gate console send reply strictly on allowed_actions`), grouped operationally with verified `order_context` 10-field contract parity (`b94df2744d4e9d57bbbc5b4ae3b29a466d886027` / `c6b0681`)
- **Prior A Audit:** [2026-11-15-console-send-permission-a.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-15-console-send-permission-a.md)
- **Verdict:** **PASS** (scoped to frontend console `allowed_actions` permission gating and grouped local runtime integration; zero production patches by C).
- **Safety / Runtime Posture:** Controlled restart via `scripts/stop-app.ps1` + `scripts/start-app.ps1 -SkipInstall -DisableLLM` preserving PostgreSQL (`55432`) and unrelated processes; `.local/ai.env` and `.local/training-cap-20261114.json` untouched; `llm_enabled: false`; `live_llm_requests_made: 0` before, during, and after all checks.

---

## 1. Frontend Build, Unit Tests, Typecheck & Impeccable Check

| Check | Command | Outcome |
| --- | --- | --- |
| TypeScript check | `pnpm --dir apps/frontend run typecheck` (`tsc -b`) | **PASS** (exit 0) |
| Vitest suite | `pnpm --dir apps/frontend test` (`vitest run`) | **PASS** (`6` files, `30` tests passed, `0` failed, `0` skipped) |
| Production build | `pnpm --dir apps/frontend run build` (`tsc -b && vite build`) | **PASS** (`dist/assets/index-C3zu942g.js`, `dist/assets/index-DoT7plPC.css`) |
| Impeccable static check | `impeccable.cmd detect --json apps/frontend/src/features/console.tsx` | **PASS** (`[]` — 0 findings) |

### Code-Level Permission Invariants Verified (`console.tsx`)

- `allowedActions = Array.isArray(ticket.allowed_actions) ? ticket.allowed_actions : []` ([console.tsx:83](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx#L83)) fails closed on absent, `null`, non-array, or empty values.
- `canSendReply = can('send_reply')` and `canComposeReply = canSendReply || can('submit_reply_proposal')` ([console.tsx:87-88](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx#L87-L88)) have zero `role`/`hasAuthority` fallback for reply sending.
- `canExecuteAction` ([console.tsx:91-100](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx#L91-L100)) and `action()` ([console.tsx:101-105](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx#L101-L105)) block handler execution and clear `dialog === 'send'` if `canSendReply` drops, while `Modal open={(dialog === 'send' && canSendReply) || ...}` ([console.tsx:123](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx#L123)) closes open dialogs immediately upon revocation.

---

## 2. Controlled Local Runtime Verification & Static Bundle Parity

- **Process guard & restart:** Inspected `.local/processes.json`, verified `stop-app.ps1` only stops recorded `uvicorn` PIDs (keeping PostgreSQL on `127.0.0.1:55432`), and launched `.\scripts\start-app.ps1 -SkipInstall -DisableLLM` (`processes.json` PIDs `12648` ai-service, `40568` backend, `StartedAt: 2026-11-15T09:49:35Z`).
- **Evidence JSON:** [runtime_readiness_check.json](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/runtime_readiness_check.json)
  - `http://127.0.0.1:8080/health/ready`: `status: "ready"`, `backend_build: "application-v1"`, `privacy_ner_available: true`.
  - `http://127.0.0.1:8080/` vs `apps/frontend/dist/`: serves exact `index.html` and `dist/assets/index-C3zu942g.js` (matching SHA-256 `ef77343dc11d9b8d1c883ff8b2af6d90fd6c61e192e07e69bb9d782d26277cbd`).
  - `http://127.0.0.1:8002/health/ready`: `status: "ready"`, `llm_enabled: false`, `live_llm_requests_made: 0`, `model_version: "fit2-supcon-energy-boundary-v1"`, `model_mode: "trained"`, `model_verified: true`, `model_checksum: "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa"`, `calibration_checksum: "782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39"`.
  - Live `8002` `POST /v1/analyses` & `POST /v1/drafts` with 10-field `order_context` (`ORDER_CONTEXT_ALLOWED_FIELDS`): analysis succeeded (`refund_status`, `0.9811`), `/v1/drafts` returned `status: "llm_unavailable"`, `failure_code: "llm_not_configured"`, `llm` latency `0 ms`, and `live_llm_requests_made` remained `0`.

---

## 3. Real-Browser Playwright Verification (`msedge` against live `127.0.0.1:8080`)

Executed [verify_console_permissions_c.mjs](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/verify_console_permissions_c.mjs) against the live `http://127.0.0.1:8080` bundle (`12/12 PASS`, `0` failed; report: [playwright_permission_verification.json](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/playwright_permission_verification.json)):

1. **`real-runtime-readonly-staff-admin`:** Real sign-in/sign-out as `staff-1` and `admin-1` (no passwords exposed, zero ticket mutations), loaded live `/console` inbox cleanly (`scrollWidth == 1440 == innerWidth`, `bodyBg == rgb(248, 250, 252)`, `0` axe WCAG 2.2 AA violations, `0` `5xx`, `0` unexpected console errors). Note: initial unauthenticated `GET /v1/sessions/current` returns `401` and browser logs CSP `font-src 'self'` for axe/Chromium `data:font/woff2` probe (non-blocking pre-existing runtime noise).
2. **`P1-contradictory-admin-escalate-only`:** `admin` with `allowed_actions: ['escalate']` has zero `Send reply` / `Submit for approval` buttons; escalation modal succeeds without any `/replies` or `/reply-proposals` POST.
3. **`P2-fail-closed-*` (`absent`, `null`, `non-array-string`, `empty`):** Even with `actor.role === 'admin'`, all four variants fail closed (`'This ticket is waiting on an administrator.'`, zero action buttons, zero action POSTs).
4. **`P3-ai-pending-safety`:** Pending AI state disables send and shows `'The AI is still working on this ticket.'`, even if `'send_reply'` is in `allowed_actions`; zero action POSTs.
5. **`P4-closed-and-own-proposal-fail-closed`:** `closed` ticket (`'Sent reply'`) and `staff` viewing own `awaiting_approval` proposal (`allowed_actions: []`) both fail closed with zero action POSTs.
6. **`P5-dynamic-revocation-between-modal-open-and-confirm`:** Opened `Send reply` confirmation modal ([modal-open-before-revocation.png](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/modal-open-before-revocation.png)), then synthetic `GET /v1/console/tickets/:id` revoked `send_reply` to `['correct_intent']` on the `10s` workspace poll -> modal closed automatically ([modal-closed-after-revocation.png](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/modal-closed-after-revocation.png)), `Send reply` removed, zero `/replies` POSTs.
7. **`P6`, `P7`, `P8` Legitimate Flows:** Verified `no_ai_draft` manual send (`POST /replies`, `basis: "no_ai_draft"`), `staff` `Submit for approval` ([staff-submit-for-approval.png](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/staff-submit-for-approval.png), `POST /reply-proposals`, `basis: "ai_draft"`), and cross-person `admin` approval send ([admin-cross-person-approval.png](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/admin-cross-person-approval.png), `POST /replies`, `basis: "reply_proposal"`). All passed axe-core WCAG 2.2 AA and `1440px` layout checks cleanly.

---

## 4. Grouped Disposable-PG Integration (`order_context` 10-Field + Authoritative Console API)

Executed [verify_grouped_disposable_e2e_c.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/verify_grouped_disposable_e2e_c.py) against an ephemeral PostgreSQL schema (`c_grouped_verify_51c42093af`, dropped on completion) + `httpx.MockTransport` AI/Gemini transport (results in [grouped_disposable_e2e_c.json](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/browser/console_send_permission_c_20261115/grouped_disposable_e2e_c.json)):

- **10-field `order_context` wire & hydration (`TCK-1001`):** Exact 10 `ORDER_CONTEXT_ALLOWED_FIELDS` transmitted over AI wire (`tracking_code` redacted), worker hydrated all 10 cited fields (`draft_status: "draft_ready"`).
- **Server-enforced `allowed_actions` (`TCK-1002`, `is_authority_required: true`):**
  - `staff-1` receives `allowed_actions: ["correct_intent", "submit_reply_proposal", "escalate"]` (`send_reply` omitted) and receives `HTTP 403` on direct `POST /replies`.
  - `staff-1` submits proposal (`POST /reply-proposals` `201`), after which `staff-1` sees `status: "awaiting_approval"` and `allowed_actions: []`.
  - `admin-1` sees `allowed_actions: ["send_reply"]`, sends `POST /replies` (`basis: "reply_proposal"`, `201`), closing the ticket (`status: "closed"`, `allowed_actions: []`).

---

## 5. Preserved Data, PG Counts & Core Invariant Hashes

- **Live PostgreSQL row counts strictly unchanged** before restart (`PRE`) and after all runtime/browser/disposable-schema checks (`FINAL`):
  `accounts=89`, `audit_log_entries=342`, `customer_messages=68`, `idempotency_records=26`, `orders=3`, `products=100`, `sessions=1`, `sign_in_failures=0`, `suggestion_jobs=78`, `suggestions=78`, `tickets=68`.
- **Live LLM zero-call guarantee:** `live_llm_requests_made: 0` (`llm_enabled: false`) confirmed on `http://127.0.0.1:8002/health/ready` after all tests.
- **All 11 pinned invariant SHA-256 digests match (`PINNED_MISMATCHES: []`) & `2/2` STOP training cap untouched** (`.local/training-cap-20261114.json` `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`, `.local/ai.env` `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`).
