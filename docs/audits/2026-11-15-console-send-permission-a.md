# Console `canSendReply` Permission Fallback Fix (A Audit Report)

- **Date:** 2026-11-15
- **Branch / Base:** `minh` (base commit `c6b0681`)
- **Scope:** Frontend console reply-permission enforcement (`apps/frontend/src/features/console.tsx`) and permission/flow regression tests (`apps/frontend/src/features/console-permissions.test.tsx`). Backend production files were read for diagnosis only and left untouched.

## 1. Root Cause Diagnosis

In `apps/backend/tickets/service.py:89-105` (`allowed_actions`), the backend omits `'send_reply'` whenever sending is disallowed (including closed tickets, non-open tickets viewed by `staff`, pending AI analysis/draft, `staff` viewing `is_authority_required` tickets, and `own_pending_proposal` under `awaiting_approval`).

Previously in `apps/frontend/src/features/console.tsx:83-86`:

```tsx
const can = (action: string) => ticket.allowed_actions.includes(action)
const isPending = suggestion?.analysis_status === 'pending' || suggestion?.draft_status === 'pending'
const readOnly = ticket.status === 'closed' || ticket.allowed_actions.length === 0
const canSendReply = can('send_reply') || (!readOnly && (hasAuthority || !ticket.is_authority_required))
```

1. **Client-side permission fallback leak:** Whenever `ticket.allowed_actions` was non-empty (`!readOnly`) yet omitted `'send_reply'` (for instance, `admin`/`manager` with `['escalate']` or `['correct_intent']`, or `staff` on a non-authority ticket with `['correct_intent']` or pending draft), `canSendReply` evaluated to `true` via `!readOnly && (hasAuthority || !ticket.is_authority_required)`, rendering the `Send reply` button (`console.tsx:107`).
2. **Absent/malformed array safety:** Calling `ticket.allowed_actions.includes(...)` and `.length` directly assumed `allowed_actions` was always an array instead of failing closed if absent/unloaded at runtime.
3. **Misleading helper/editor state & handler guard:** When `allowed_actions` contained non-send actions such as `['escalate']` or `['correct_intent']` without `'send_reply'` or `'submit_reply_proposal'`, the reply helper could display `'Review complete. Your reply is ready to send.'` with draft edit/reject controls visible, and `action(...)` (`console.tsx:89`) had no fail-closed permission/blocker re-check before invoking `post(...)`.

The prior test suite in `apps/frontend/src/features/console-permissions.test.tsx:41-50` masked this defect because test 1 (`openTicket(['correct_intent'])`) only checked `if (send) expect(send).toBeDisabled()`, and test 2 (`openTicket(['correct_intent'], true)`) relied on the fallback rendering `Send reply` even though `'send_reply'` was omitted.

## 2. Minimal Patch Applied

### `apps/frontend/src/features/console.tsx`
- Normalized `allowedActions = Array.isArray(ticket.allowed_actions) ? ticket.allowed_actions : []` so absent/malformed permissions fail closed (`can(...) === false`, `readOnly === true`).
- Removed the role/authority fallback: `const canSendReply = can('send_reply')` and `const canComposeReply = canSendReply || can('submit_reply_proposal')`.
- Gated `warning` acknowledgements, draft edit/reject buttons, `<div className="reply-editor">`, and ready helper copy (`'You cannot send a reply on this ticket.'` vs `'Review complete. Your reply is ready to send.'`) on `canComposeReply`.
- Added `canExecuteAction(name, payload)` inside `action(name, payload)` (`console.tsx:91-105`) so `'replies'`, `'reply-proposals'`, `'escalations'`, and `'suggestions'` (`correct_intent` vs `retry_suggestion`) cannot call `post(...)` when unauthorized, blocked, or busy, and gated modal `open` props (`send`, `proposal`, `escalate`, `intent`, line `123`) on live `can(...)` checks so a background refresh revoking permissions closes any stale confirmation dialog.
- Preserved light theme styling (`achromatic-ledger`), `replyBasis`/`replyBlocker` rules, manual/proposal/escalation controls, and `awaiting_approval` proposal review flow.

### `apps/frontend/src/features/console-permissions.test.tsx`
Added/updated 8 Vitest integration tests covering:
1. Omitted `'send_reply'` on ready ticket (`['correct_intent']`) hides `Send reply`, draft edit/reject, and ready helper copy.
2. Contradictory `admin`/`manager` roles on `open` (`['escalate']`) and `escalated` (`['correct_intent']`) tickets hide `Send reply` while keeping allowed `Escalate ticket`.
3. Empty (`[]`), `undefined`, and `null` `allowed_actions` fail closed (`Send reply` absent, `'This ticket is waiting on an administrator.'`).
4. Pending suggestion: `'correct_intent'` without `'send_reply'` hides `Send reply`; `['correct_intent', 'send_reply']` renders `Send reply` disabled with `'The AI is still working on this ticket.'`.
5. `closed` tickets and `awaiting_approval` own proposals (`allowed_actions: []` as `admin`) fail closed with read-only proposal text.
6. Granted `'send_reply'` enables sending, and revoking `'send_reply'` via query invalidation closes an already-open confirm modal without posting `/replies`.
7. Staff `'Submit for approval'` (`reply-proposals`) and another admin's proposal approval send (`replies` with `basis: 'reply_proposal'`) remain intact.
8. Manual (`basis: 'no_ai_draft'` + PII `[NAME]` block), rejected draft (`basis: 'rejected_ai_draft'`), escalation (`escalations`), and raw uncalibrated score rendering remain intact.

## 3. Verification Results

All checks ran after the final edits on `apps/frontend/src/features/console.tsx` and `apps/frontend/src/features/console-permissions.test.tsx`:

| Check | Scope / Command | Result |
| --- | --- | --- |
| `vitest run` | `Set-Location apps/frontend; npm test` | **Passed:** 6 test files, 30/30 tests (`reply-rules.test.ts` 3, `console.test.tsx` 9, `support.test.tsx` 2, `reports.test.tsx` 3, `unified-console.test.tsx` 5, `console-permissions.test.tsx` 8) |
| TypeScript | `npm run typecheck` (`tsc -b`) | **Passed:** 0 errors |
| Production Build | `npm run build` (`tsc -b && vite build`) | **Passed:** built `dist/index.html`, `dist/assets/index-C3zu942g.js` (453.63 kB), `dist/assets/index-DoT7plPC.css` (45.69 kB) |
| Impeccable Detector | `impeccable.cmd detect --json apps/frontend/src/features/console.tsx` | **Passed:** `[]` (0 findings) |
| Real-Browser Playwright Check | Built `apps/frontend/dist` served temporarily via `vite preview --host 127.0.0.1 --port 4179` + Playwright headless `msedge` with intercepted `/v1/...` API routes | **Passed:** contradictory `admin` + `['escalate']` hid `Send reply` & kept `Escalate ticket` (`scrollWidth <= innerWidth`, `'You cannot send a reply on this ticket.'`); empty `allowed_actions: []` failed closed; pending + `['send_reply']` disabled `Send reply`; granted `['correct_intent', 'send_reply', 'escalate']` enabled send and submitted `POST /v1/console/tickets/TCK-BROWSER-1/replies` (`basis: 'ai_draft'`); 0 console/page errors |

## 4. Known Limits & Unchanged Components

- **Backend untouched:** `apps/backend/tickets/service.py` and backend endpoints were not modified (`git diff` touches only `console.tsx` and `console-permissions.test.tsx`, plus this audit file).
- **Live shared services untouched:** Existing shared running backend/AI/frontend servers were not restarted or hit with live LLM/send requests; Playwright verified the newly built `dist/` bundle via an isolated `vite preview` server with mocked `/v1/**` responses, so live end-to-end backend static-serve verification remains for coordinator/C rebuild-and-restart verification if desired.
