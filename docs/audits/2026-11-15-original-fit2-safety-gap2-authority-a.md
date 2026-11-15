# Safety Gap 2 Audit — Authority & Outage + Reason-Codes Contract (Slice 2A)

- **Date:** 2026-11-15
- **Branch:** `minh` (on top of closed Slice 1)
- **Scope:** First slice of Gap 2 — backend authority enforcement across AI outage/timeout/pseudonymization failure, role-promotion self-approval hardening, and `Engine` / `AI_REASONS` contract verification (no `apps/core_backend/safety.py` or `Engine` edits).

## 1. Call Paths & Defects Reproduced (TDD RED)

Three backend authority gaps were identified and reproduced before editing `apps/backend/tickets/service.py`:

1. **Duplicate narrow regex `SENSITIVE_KEYWORDS` in `apps/backend/tickets/service.py`:**
   - `create_ticket()` (`apps/backend/tickets/service.py`) and `create_suggestion()` (`apps/backend/tickets/service.py`) previously used a narrow local regex (`fraud|lawsuit|legal action|chargeback|unauthorized transaction|policy exception`) instead of the shared normative `has_authority_request` helper from `apps.core_backend.safety`.
   - Under AI outage (`ai_service_base_url=None`), `ml_timeout`, `pseudonymize()` failure (`pseudonymization_failed`), or bogus `ai_service` responses (`recommendation="draft"`, `reason_codes=[]`), customer messages such as `"make an exception"`, `"lawyer"`, `"grant an exception"`, `"bank dispute"`, `"unauthorized charges"`, `"manager exception"`, and `"human manager"` left `Ticket.is_authority_required == False`, allowing `staff` to send direct `/replies` (`201`) instead of receiving `403 authority-required`.
2. **Role-promotion self-approval loophole (`allowed_actions` + `act` in `apps/backend/tickets/service.py`):**
   - When a `staff` user submitted a `reply-proposal` (`ticket.status == "awaiting_approval"`), was promoted to `manager` via `change_account` (`POST /v1/console/admin/role-changes` — revoking old sessions to `401`), and logged back in as `manager`, `allowed_actions()` still returned `"send_reply"` and `act()` only checked `body["basis"] == "reply_proposal"` after `validate_reply()`. That allowed the promoted proposer to bypass `403 self-approval-forbidden` by sending `POST /replies` with `basis="no_ai_draft"`, `"ai_draft"`, or `"rejected_ai_draft"`.

**TDD RED Run (`tests/application/test_gap2_authority_outage_a.py`):**
- Command: `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap2_authority_outage_a.py -v --tb=line`
- Result: **`11 failed, 1 passed in 17.94s`** (all 7 authority phrase cases failed with `is_authority_required=False`, sticky timeout/privacy failed, role promotion returned `"send_reply"` in `allowed_actions`, concurrent downgrade check failed, and quoted `lawyer` failed closed check).

## 2. Changes Applied (`apps/backend/tickets/service.py`)

Keeping Slice 1 files completely untouched (`apps/core_backend/safety.py`, `apps/core_backend/retrieval/adapter.py`), four minimal changes were made in `apps/backend/tickets/service.py`:

1. Replaced `SENSITIVE_KEYWORDS` with `from apps.core_backend.safety import has_authority_request`.
2. **`create_ticket()`**: initializes `message_requires_authority = has_authority_request(message)` before any suggestion job or worker runs.
3. **`create_suggestion()`**: retains sticky OR logic (`if intent_override in SENSITIVE_ACTION_INTENTS or has_authority_request(body_text): ticket.is_authority_required = True`) prior to queuing/running AI work, surviving `pseudonymize()` failure, pending/unavailable drafts, late analysis, or staff intent overrides.
4. **`allowed_actions()` & `act()`**:
   - `allowed_actions()` computes `own_pending_proposal = ticket.status == "awaiting_approval" and (ticket.proposal or {}).get("actor_account_id") == actor.account_id` and suppresses `"send_reply"` when `own_pending_proposal` is true.
   - `act()` enforces `raise Problem(403, "self-approval-forbidden", ...)` BEFORE `validate_reply()` whenever `action == "replies"` and `(ticket.status == "awaiting_approval" or body.get("basis") == "reply_proposal") and (ticket.proposal or {}).get("actor_account_id") == actor.account_id`, blocking direct `no_ai_draft` / `ai_draft` / `rejected_ai_draft` / `reply_proposal` bypasses by a promoted proposer.

## 3. Verification Results (TDD GREEN & Regression)

- **Targeted Suite (`tests/application/test_gap2_authority_outage_a.py`):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap2_authority_outage_a.py -v`
  - Result: **`12 passed in 20.57s`**
  - Coverage includes:
    - 7 `has_authority_request` phrasings under AI offline (`403 authority-required` for `staff`, allowed for `manager`)
    - Sticky authority under pending analysis, `ml_timeout`, bogus `recommendation="draft"`, `reason_codes=[]`, and `pseudonymization_failed`
    - Role promotion (`staff -> manager`): old session revoked (`401`), new `manager` blocked from `"send_reply"` in `allowed_actions`, and `403 self-approval-forbidden` on direct `/replies` (both `reply_proposal` and `no_ai_draft`) while another `manager` can approve
    - Concurrent `ThreadPoolExecutor(3)` `SuggestionWorker.store()` with routine `draft` never downgrades `Ticket.is_authority_required`
    - Controls: normative negations (`is_authority_required=False`), cross-customer `404`, idempotent replay, `AuditEntry.event_type` (`ticket.created`, `reply.sent`), quoted `lawyer` (`has_authority_request == True`), and bounded `AI_REASONS` contract
- **Focused Regression Suite:**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/application/ tests/unit/test_suggestion_worker_concurrency.py tests/unit/test_mandatory_routing_b.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_safety_slice1_gap1_a.py -v`
  - Result: **`382 passed in 160.59s (0:02:40)`** (zero failures, zero skips).

## 4. `Engine` /Gateway vs `jobs.AI_REASONS` Contract Inventory

- Verified `apps/backend/tickets/jobs.py` `AI_REASONS` contains **29** bounded reason codes:
  `['ai_service_unavailable', 'budget_exceeded', 'conflicting_sources', 'encoder_failed', 'encoder_failure', 'encoder_unavailable', 'explicit_human_request', 'grounding_failed', 'human_agent_requested', 'insufficient_evidence', 'invalid_model_output', 'llm_insufficient_evidence', 'llm_invalid_output', 'llm_rate_limited', 'llm_timeout', 'llm_unavailable', 'low_confidence', 'low_margin', 'missing_information', 'ml_error', 'ml_timeout', 'ml_unavailable', 'no_valid_document', 'only_expired_documents', 'out_of_scope_intent', 'requires_authority', 'selective_rejected', 'signal_disagreement', 'source_review_overdue']`
- Every `reason_code` emitted by `apps/ai_service/engine.py` (`Engine._analyse` / `Engine.draft`) and `apps/ai_service/main.py` is already present in `jobs.AI_REASONS` (0 drift), so no edits to `apps/core_backend/safety.py` or `apps/backend/tickets/jobs.py` were needed.
- Router-only codes (`recognized_outside_product_scope`, `missing_order_id`, `max_clarify_reached`, `policy_not_approved`) remain confined to `apps/core_backend/intent/routing.py` (`decide_route` / `PipelineRunner`).

## 5. Invariant Checksums & Untouched Boundary Check

`git diff --stat HEAD -- apps/core_backend/ apps/ai_service/` returned empty (no modifications).

| Artifact | Verified SHA-256 |
| --- | --- |
| `apps/core_backend/safety.py` | `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000` |
| `apps/core_backend/retrieval/adapter.py` | `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` |
| `data/knowledge/approved_kb.v2.json` | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` |
| `apps/ai_service/kb-release.json` | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors` | `f695b1fe514aba81aafc968823047496b03474a0b47199c65eaac6bd93c6dfa` |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json` | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| `artifacts/models/trained/distilbert-supportiq/model.safetensors` | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| `.local/training-cap-20261114.json` | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` |
| `.local/ai.env` | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` |

## 6. Deferred Follow-Up & Remaining Limits (Not Bundled)

- **Minimal `Engine` `order_context` slot parity proposal (not edited here):** `apps/ai_service/engine.py` (`Engine._analyse`) currently does not replicate `decide_route`'s `PERSONAL_ORDER_REQUIRED` / `missing_order_id` clarifying-question slot gate (`apps/core_backend/intent/routing.py`). A future focused slice can pass `order_context` / `order_id` availability into `Engine._analyse()` and map `missing_order_id` cleanly in `jobs.AI_REASONS` if clarifications are required on AI service paths.
- **Remaining out-of-scope items:**
  - **Gap 3 (NER / pseudonymization quality):** `pseudonymize()` failures remain fail-closed (`pseudonymization_failed` + sticky authority check where applicable), without modifying `.privacy` / NER models in this slice.
  - **Raw Fit2 classifier & `has_authority_request` lexical limits:** Backend authority relies on normative `has_authority_request` (e.g., benign/quoted `"lawyer"` stays conservative `True`) plus sticky intent/worker flags; raw Fit2 model calibration and training weights remain unchanged.
