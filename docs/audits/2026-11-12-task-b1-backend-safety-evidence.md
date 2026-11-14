# SupportIQ — Task B1 Backend Safety, Authority & Privacy Evidence Report

**Date:** 2026-11-12  
**Worker:** Backend Worker 1 (Task B1)  
**Worktree Branch:** `MINHDZVODICH/supportiq-backend-safety-v2`  
**Base Commit:** `6dbd8ae`  
**Target Scope:** `apps/backend/tickets/` and dedicated application safety/privacy tests  

---

## 1. Executive Summary & Delegated Stakeholder Authority

Under delegated stakeholder authority from the coordinator and user instructions:
- Preserved existing ticket, jobs, audit, and gateway transport interfaces without backwards-incompatible API changes.
- Traced Functional Requirements FR-04 through FR-08, closing five concrete safety, workflow authority, and data privacy gaps.
- Verified all behaviors against native PostgreSQL in disposable schemas using Python driver `PSYCOPG_IMPL=python` and `F:/PostgreSQL/bin` on Windows PATH without modifying coordinator checkout or running services.

---

## 2. Gaps Closed & Technical Implementations

### Gap 1: Sticky Manager Authority After Intent Override & Async Retry (FR-06)
- **Problem:**
  - Previously, `create_ticket` defaulted `is_authority_required=False` regardless of whether the customer message reported chargeback, fraud, or legal disputes.
  - `create_suggestion` only flagged `request_refund`, ignoring other sensitive intents (`cancel_order`, `return_product`, `payment_issue`) and message keywords.
  - During asynchronous retries (`act(..., action="suggestions", body={})`), previous staff `intent_override` values were discarded.
- **Fix:**
  - Added `SENSITIVE_KEYWORDS = re.compile(r"\b(fraud|lawsuit|legal action|chargeback|unauthorized transaction|policy exception)\b", re.I)`.
  - Added `SENSITIVE_ACTION_INTENTS = {"cancel_order", "request_refund", "return_product", "payment_issue"}`.
  - In `create_ticket`, initial messages matching sensitive keywords immediately initialize `is_authority_required=True`.
  - In `create_suggestion`, authority requirement is sticky: any sensitive intent override or sensitive customer message activates `is_authority_required=True` immediately.
  - In `act`, asynchronous retries preserve the ticket's active `intent_override` if no new override is specified.
  - In `jobs.py`, `SuggestionWorker.store` guarantees that once a ticket has `is_authority_required=True`, it remains true across subsequent suggestion updates.
  - Verified that staff direct send is blocked with HTTP 403 (`authority-required`); staff must submit a proposal (`/reply-proposals`), which only a manager can approve and send.

### Gap 2: Duplicate Send Under Concurrency (FR-04, FR-08)
- **Status:** Existing Architectural Behavior Newly Verified (No Production Code Changes Required).
- **Background & Verification:**
  - SupportIQ's existing architecture enforces idempotency and transaction boundaries through two layers:
    1. Transactional row-level lock `with_for_update()` in `require_ticket()`.
    2. PostgreSQL transactional advisory lock `pg_advisory_xact_lock()` in `idempotent()`.
  - Previously, test coverage only exercised distinct idempotency keys across serialized requests, leaving simultaneous identical-key requests and distinct-key rapid race conditions unexercised under concurrency.
  - Added concurrent `ThreadPoolExecutor` integration tests verifying existing production behavior:
    - **Identical Idempotency-Key:** Concurrent requests return identical HTTP 201 responses with identical `reply_id`. Exactly one reply is recorded in `tickets` and exactly one `reply.sent` audit entry is created.
    - **Distinct Idempotency-Keys:** Exactly one request receives HTTP 201; the conflicting concurrent request receives HTTP 409 (`invalid-ticket-state: A colleague already sent the reply.`).
  - **Conclusion:** No production code modifications were needed or added for concurrency; existing safeguards are now formally verified with multi-threaded test coverage.

### Gap 3: Manual Fallback on AI Errors (FR-05, FR-08)
- **Problem:**
  - When the AI service failed on analysis (503 / timeout / connection error), the worker left `draft_status` as `pending` and redundantly attempted a draft request, causing unnecessary latency before manual handling was unblocked.
  - If draft generation failed, `staff_note` guidance was missing.
- **Fix & Fact-Safe Verification:**
  - In `SuggestionWorker.process`, if analysis fails (`analysis_res is None`), the worker immediately fails closed, records both analysis and draft as `unavailable`, sets `staff_note="The AI service is unavailable. Review the customer message and order records to write a reply manually."`, and finishes the job without attempting a doomed draft call.
  - If analysis succeeds but drafting fails (`draft_res is None`), the worker retains the retrieved policy sources and sets `staff_note="Draft generation is unavailable. Review the retrieved sources and write a reply manually."`.
  - If worker retries are exhausted (`attempts >= 3`), `staff_note` provides explicit manual fallback guidance.
  - In `service.py`, `validate_reply` allows `basis="no_ai_draft"` whenever AI is unavailable or abstained. If authority is required, staff can submit a manual proposal for manager approval.
  - **Fact-Safe Manual Reply Test:** Verified that staff immediately sends fact-safe manual acknowledgement and investigation notes (e.g. acknowledging damaged packaging and confirming investigation with fulfillment) without inventing fabricated shipping status or claiming unverified replacement dispatch.

### Gap 4: Audit Immutability Under Deployment Grants and Owner Triggers (FR-07, FR-08)
- **Problem:**
  - Prior immutability tests only executed as database owner, without exercising the least-privilege `supportiq_app` runtime role or verifying actual deployment grant definitions.
- **Fix & Verification:**
  - **Deployment Grant Definition Assertion:** Added automated assertions on `apps/backend/manage.py` verifying that canonical deployment grants to `supportiq_app` strictly omit `UPDATE` and `DELETE` on `audit_log_entries` and `customer_messages`, restricting permissions to `SELECT` and `INSERT`.
  - **Disposable Schema Bootstrap:** Bootstrapped the exact deployment grant statements from `apps/backend/manage.py` inside the disposable test schema using a safely disposed engine (`grant_engine.dispose()`).
  - **Explicit Skip Semantics:** If `database_url_app` is absent from `.local/application.json`, the test explicitly skips (`pytest.skip("Runtime-role NOT verified: database_url_app is absent in credentials configuration")`), preventing false-positive claims of runtime coverage.
  - **Multi-Role Enforcement:**
    - **Owner Role (`supportiq_owner`):** PostgreSQL `immutable_record` row triggers block `UPDATE` and `DELETE` on `audit_log_entries` and `customer_messages` with exception `'Append-only record'`.
    - **Runtime Role (`supportiq_app`):** PostgreSQL privilege grants deny `UPDATE` and `DELETE` permissions at the database engine level (SQL 42501). Verified that `supportiq_app` can execute `SELECT` and `INSERT` on `audit_log_entries`, but is strictly forbidden from mutating or deleting records. All engines are safely disposed in `finally` blocks.

### Gap 5: Outbound Gateway Transport Synthetic PII & Log Redaction (FR-08)
- **Problem:**
  - Prior tests only ran unit helper simulations of `pseudonymize()` without exercising the application API, background worker, or inspecting HTTP transport payloads.
- **Fix & Verification:**
  - Implemented boundary test `test_actual_outbound_gateway_transport_synthetic_pii_and_log_capture`:
    - Customer submits ticket through `/v1/shop/tickets` with complete synthetic PII (name, phone, email, physical address, Luhn-valid credit card, order ID, tracking code, transaction code, customer-typed literal placeholder `[NAME_1]`).
    - Captured the exact outbound HTTP request payload sent by `SuggestionWorker` across the transport to the AI gateway.
    - Verified zero raw synthetic PII in outbound transport payload: all identifiers replaced with typed pseudonym tokens (`[NAME_1]`, `[PHONE_1]`, `[EMAIL_1]`, `[CARD_1]`, `[ORDER_ID_1]`, `[TRACKING_ID_1]`, `[ADDRESS_1]`, `[LITERAL_1]`).
    - Verified outbound `order_context` across transport contains only allowlisted fields (`order_status`, `order_total`, `shipping_cost`, `shipment_status`, `refund_status`, `refund_amount`) and zero PII.
    - Captured structured application logs: verified zero raw card numbers, phone numbers, email addresses, or unredacted credentials.
  - Added boundary test `test_documented_recall_boundary_on_informal_slang`:
    - Documented honest recall boundary: uncataloged colloquial Vietnamese vernacular without standard administrative keywords is not recognized without spaCy NER.

---

## 3. Test Verification & Exact Counts

### Focused Safety & Application Suite
Command executed in disposable PostgreSQL schemas:
```powershell
$env:PSYCOPG_IMPL="python"; $env:PATH="F:\PostgreSQL\bin;" + $env:PATH; $env:SUPPORTIQ_APPLICATION_SECRETS="F:/Năm 3/SD/project/SupportIQ/.local/application.json"; python -m pytest tests/application/ tests/unit/test_privacy_pii.py tests/unit/test_retry_draft.py
```
**Result:** **60 passed, 1 skipped** (12.68s)  
- `tests/application/test_backend_safety_closure.py`: 10 passed
- `tests/application/test_application.py`: 20 passed
- `tests/application/test_ai_boundary.py`: 12 passed
- `tests/application/test_workflow_privacy.py`: 5 passed
- `tests/application/test_current_kb.py`: 2 passed
- `tests/application/test_llm_retry.py`: 2 passed
- `tests/unit/test_privacy_pii.py`: 7 passed, 1 skipped (optional live spaCy model skip)
- `tests/unit/test_retry_draft.py`: 2 passed

### Full Application Test Suite
```powershell
$env:PSYCOPG_IMPL="python"; $env:PATH="F:\PostgreSQL\bin;" + $env:PATH; $env:SUPPORTIQ_APPLICATION_SECRETS="F:/Năm 3/SD/project/SupportIQ/.local/application.json"; python -m pytest tests/application/
```
**Result:** **51 passed** (77.63s)

---

## 4. Remaining Project Gates (Outside Task B1 Ownership)

1. **Task B2 (Retrieval & Policy Grounding):** Knowledge Base gold alignment and routing policy hash verification in `data/benchmarks/`.
2. **Task B3 (Acceptance Runner & ML Provenance):** 10-fold ML cross-validation provenance and latency/cost benchmarks under declared pricing.
3. **Task F1 (Frontend):** Light theme refinement, accessibility checks (axe/overflow), and multi-width mobile review.
