# Security & Semantic Review B: Safety Gap 2 — Authority, Outage Persistence & Role-Promotion Self-Approval (`f93b7882`)

- **Reviewer:** Worker B (Security & Semantic Review)
- **Target Commit:** `f93b7882960ebd351eadff72543f5cf78aafd211` on branch `minh`
- **Baseline:** `40c734389cbfe18d86ecb7d38b8407cb60494e50` (Slice 1 closure)
- **Verdict:** **PASS**

## 1. Diff & Invariant Verification

`git diff --name-only 40c73438..f93b7882` touches only:
- `apps/backend/tickets/service.py` (`+7/-6` net lines)
- `tests/application/test_gap2_authority_outage_a.py` (`+440` lines)
- `docs/audits/2026-11-15-original-fit2-safety-gap2-authority-a.md` (`+76` lines)

SHA-256 digests verified unchanged from baseline:
- `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
- `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
- `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
- `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
- `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`

## 2. Security & Semantic Findings

1. **Canonical Detector & Removal of `SENSITIVE_KEYWORDS` (PASS):**
   - Repo-wide search across `apps/`, `tests/`, `scripts/`, and `pipeline/` found `0` remaining references to `SENSITIVE_KEYWORDS`.
   - `apps/backend/tickets/service.py` imports `has_authority_request` from `apps.core_backend.safety` (which imports only Python stdlib modules, L5–9). Clean imports in both module orders (`safety -> service -> main` and `service -> safety -> main`) succeed with no circular import.
   - `SENSITIVE_ACTION_INTENTS` (`cancel_order`, `request_refund`, `return_product`, `payment_issue`) in `service.py:17` matches `sensitive_action_intents` in `intent_policy.v2.json:20-25`.
2. **Pre-AI Authority Flagging & Monotonic Sticky-OR Persistence (PASS):**
   - `create_ticket` (`service.py:148-154`) sets `is_authority_required = has_authority_request(message)` at intake before `create_suggestion`.
   - `create_suggestion` (`service.py:126-128`) executes after `pseudonymize` (catching `ValueError`) and before any worker dispatch, setting `ticket.is_authority_required = True` when `intent_override in SENSITIVE_ACTION_INTENTS or has_authority_request(body_text)`. It never assigns `False`.
   - `SuggestionWorker.store` (`apps/backend/tickets/jobs.py:374-410`) acquires row locks (`.with_for_update()`) on `Ticket` and `SuggestionJob`, validates `current_suggestion_id`, `lease_token`, and `lease_until`, and only escalates `ticket.is_authority_required = True` when `"requires_authority"` is present (`L408-409`). PostgreSQL trigger `sticky_authority` (`apps/backend/platform/database.py:50-59`) enforces no `True -> False` downgrade at the DB layer.
3. **Staff Manual Send Block, Benign Control & Role-Promotion Self-Approval Prevention (PASS):**
   - Staff direct send on `is_authority_required=True` raises `403 authority-required` (`service.py:246-247`) regardless of AI availability, timeout, pending state, or pseudonymization failure, with no `Reply` or `reply.sent` audit written.
   - Normal non-authority staff sends, legacy `manager`/`admin` manual sends, and third-party proposal approvals remain functional.
   - Role promotion (`POST /v1/admin/accounts/{id}/role-changes`) invalidates prior `SessionRecord` rows (`apps/backend/accounts/service.py:95`), and `authenticate` (`accounts/service.py:61`) rejects mismatched `account.role != record.role`. Once re-authenticated as `manager`, `allowed_actions` (`service.py:78-79`) returns `[]` for the author's own `awaiting_approval` proposal (matching `apps/frontend/src/features/console.tsx:85-86,107`), and `act()` (`service.py:250-251`) rejects direct sends (`no_ai_draft`, `ai_draft`, `rejected_ai_draft`) as well as `reply_proposal` with `403 self-approval-forbidden`.
4. **Error Ordering (`403` vs `409`/`422`), Locking & Isolation (PASS):**
   - `act()` (`service.py:210-252`) acquires `FOR UPDATE`, checks `closed` (`409 invalid-ticket-state`, `L213-214`) to prevent duplicate replies, checks `actor.role == "staff" and ticket.status != "open"` (`403 forbidden`, `L215-216`), and checks `authority-required` (`403`, `L246-247`) and `self-approval-forbidden` (`403`, `L250-251`) **before** `validate_reply` (`409 suggestion-pending`, `409 suggestion-superseded`, `422 invalid-request`). `409`/`422` cannot mask `403` authority or self-approval denials.
   - PG advisory lock idempotency (`database.py:78-90`) and cross-customer `404` checks (`require_ticket(..., customer_id=...)`) are preserved.
5. **Bounded `AI_REASONS` Contract (PASS):**
   - `AI_REASONS` (`jobs.py:34-43`, 29 codes) covers all routing/draft/fault codes emitted by `Engine._analyse`/`draft`, `apps/ai_service/main.py:_BOUNDED_GATEWAY_CODES`, `jobs.py:_BOUNDED_REMOTE_FAULT_CODES`, and `safety.py:classify_retrieval_fault`, while unknown codes fail closed in `validate_analysis` (`jobs.py:91-92`). Note: internal `evaluate_text_safety` emits `recognized_outside_product_scope`, which `Engine._analyse` (`engine.py:93-105`) maps to `out_of_scope_intent`.

## 3. Independent Verification Executed on `f93b7882`

- `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap2_authority_outage_a.py -v`: **12 passed** (`19.29s`).
- `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap2_authority_outage_a.py tests/application/test_unified_console_permissions.py tests/application/test_backend_safety_closure.py tests/application/test_workflow_privacy.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_suggestion_worker_concurrency.py tests/unit/test_schema_constraints.py -q`: **46 passed** (`84.00s`).
- `npm --prefix apps/frontend test -- --run src/features/console-permissions.test.tsx`: **5 passed** (`src/features/console-permissions.test.tsx`, `29.93s`).
- Independent PostgreSQL + FastAPI `TestClient` adversarial probe (`probe_gap2_authority_b.py` in scratch): **ALL ADVERSARIAL PROBES PASSED** — verified clean import ordering, `SENSITIVE_ACTION_INTENTS`/policy parity, gateway & retrieval fault code containment in `AI_REASONS`, `403` precedence over `409`/`422`, `escalated` and `closed` state handling, `intent_override` escalation across all 4 sensitive intents, and `staff -> manager` promotion rejection across all 4 reply bases (`reply_proposal`, `no_ai_draft`, `ai_draft`, `rejected_ai_draft`) alongside permitted cross-staff approval.

## 4. Residual & Deferred Items (Outside Gap 2 Scope)

- **Gap 3 (NER / Pseudonymization):** Unaddressed and remains open in a separate slice.
- **Deferred `Engine` `order_context` slot parity:** `apps/backend/tickets/service.py:38-44` still builds 6 fields (`order_status`, `order_total`, `shipping_cost`, `shipment_status`, plus optional `refund_status`, `refund_amount`), omitting 4 timestamp fields allowed by `ORDER_CONTEXT_ALLOWED_FIELDS` in `apps/core_backend/llm/gemini.py:418-429` (`placed_at`, `estimated_delivery_at`, `delivered_at`, `refund_requested_at`).
- **Normative lexical scope of `has_authority_request`:** Intentional policy rule in `apps/core_backend/safety.py:148-165` flags non-negated authority/legal keywords (including hypothetical/quoted mentions), requiring administrator review before sending.
