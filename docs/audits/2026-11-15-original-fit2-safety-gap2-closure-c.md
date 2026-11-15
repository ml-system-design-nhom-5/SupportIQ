# Worker C Audit — Safety Gap 2 Security & API Closure (`f93b7882` / `5188d5ba`)

- **Verdict:** **PASS** — **Safety Gap 2 CLOSED** (scope: **Gap 2 backend authority/outage/self-approval only**, NOT raw ML `0.857307` and NOT whole project).
- **Branch / Reviewed HEAD:** `minh` @ `5188d5ba23994771212d8ca6aa736eb5671d941d` (Worker B PASS review over Worker A fix `f93b7882960ebd351eadff72543f5cf78aafd211`).
- **Artifacts (`artifacts/evaluation/original_fit2_gap2_authority_c_20261115/`):**
  - Pre-frozen case matrix (`frozen_gap2_case_matrix.json`, SHA `a0a7602d8af284b4e1945054d686f34ad0ba76ea268703ca4b872fa9786190f3`)
  - Runner (`evaluate_gap2_authority_c.py`, SHA `f5f2a719a5c035782b50df1a2fc281718d08867232bc6627dfc0b4b19ea6d00b`, `duration_seconds=47.63`)
  - Results (`gap2_security_verification.json` `9b89d16717c61fdb4902c9ad9385f00f727868e7bb7e9a12a071a1ec73f5d068`, `run_manifest.json`)
  - Executed strictly against **isolated disposable PostgreSQL schemas** (`test_gap2_c_*`, dropped via `CASCADE` on exit) seeded with synthetic data; zero production/real-customer writes, zero app restarts, zero leaked secrets.

---

## 1. Test Runs & Invariants Verified

| Check | Command | Observed Result |
|---|---|---|
| Backend Gap 2 + Concurrency + Safety Regression | `.venv/Scripts/python.exe -B -m pytest tests/application/test_gap2_authority_outage_a.py tests/application/test_unified_console_permissions.py tests/application/test_backend_safety_closure.py tests/application/test_workflow_privacy.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_suggestion_worker_concurrency.py tests/unit/test_schema_constraints.py -q` | **46 passed** (`81.76s`) |
| Frontend Console Permissions | `npm --prefix apps/frontend test -- --run src/features/console-permissions.test.tsx` | **5 passed** (`1.85s`) |
| Independent PG + FastAPI Gap 2 Security Matrix | `.venv/Scripts/python.exe -B artifacts/evaluation/original_fit2_gap2_authority_c_20261115/evaluate_gap2_authority_c.py` | **19/19 PASS** (`47.63s`, `failed_cases=[]`) |

- **Diff since Slice 1 closure (`40c73438..5188d5ba` on `apps/`, `data/`):** `["apps/backend/tickets/service.py"]` only; `0` remaining `SENSITIVE_KEYWORDS` references in `apps/`.
- **Frozen SHA-256 invariants unchanged:** `safety.py` (`45d11761...`), `adapter.py` (`3bd797da...`), Orig Fit2 weights (`f695b1fe...`) & calibration (`782c88db...`), serving weights (`dc7af8cf...`), `approved_kb.v2.json` (`f8dcfbbd...`), `kb-release.json` (`cf450a72...`), `intent_policy.v2.json` (`8789ee26...`), `.local/training-cap-20261114.json` (`bc0445e0...`, `2/2` `STOP`), `.local/ai.env` (`26d083c7...`). Existing raw ML metrics (`noise420` `macroF1=0.857307`, `bare=267`) are unaffected.

---

## 2. Independent Frozen Security Matrix (`19/19 PASS`)

| Group | Cases | Key Observed API & DB Proof |
|---|---:|---|
| **A. Authority & Outage / Sticky OR** (`g2-auth-*`) | **8/8** | AI off (`3` shared normative phrases: bank dispute / grant exception / attorney legal), AI pending (`g2-auth-pend-01`), `ml_timeout` (`g2-auth-timeout-01`), `pseudonymization_failed` (`g2-auth-privfail-01`), sensitive `intent_override=request_refund` (`g2-auth-override-01`), and benign override + bogus `draft_ready` (`g2-auth-sticky-01`): `is_authority_required=True` sticky (`0` downgrades), `send_reply` omitted, staff direct `POST /replies` rejected **`403 authority-required`** (`0` `Reply` rows persisted, `0` `reply.sent` audits). |
| **B. Proposal, Approval & Role Promotion** (`g2-prop-*`, `g2-promo-*`) | **4/4** | Other `manager-1` (`g2-prop-manager-01`) & legacy `admin-1` (`g2-prop-admin-01`) approve proposals (`201`, `closed`). On `staff-1 -> manager` promotion (`role-changes`) with `draft_ready` active on **both** authority (`g2-promo-self-auth-4bases`) and normal (`g2-promo-self-normal-4bases`) tickets: pre-promotion session revoked (`401`), promoted `allowed_actions=[]`, and all **4** `ReplyInput.basis` paths (`reply_proposal`, `no_ai_draft`, `ai_draft`, `rejected_ai_draft`) rejected **`403 self-approval-forbidden`** (`0` `Reply` rows persisted), then cleanly approved by `manager-1` (`201`). |
| **C. Controls, Isolation, Races & Reason Contract** (`g2-ctrl-*`, `g2-conc-*`, `g2-contract-*`) | **7/7** | Normal & negated controls (`g2-ctrl-normal-01`, `g2-ctrl-neg-01`) reply `201` (`is_authority_required=False`); cross-customer ticket/order access returns `404` & customer->console returns `403` (`g2-ctrl-crosscust-01`); idempotent `POST /replies` replays `201` cleanly with `1` `reply.sent` audit and different-body reuse returns `409 idempotency-key-reused` (`g2-ctrl-idemp-01`); concurrent `ThreadPoolExecutor(2)` replies return `[201, 409]` + late `reply-proposals` returns `409 invalid-ticket-state` (`g2-ctrl-closedrace-01`); `ThreadPoolExecutor(3)` `SuggestionWorker.store()` keeps `is_authority_required=True` and direct PG `UPDATE tickets SET is_authority_required=FALSE` raises `sticky_authority` trigger exception (`g2-conc-worker-01`); `AI_REASONS` exact `29` codes, `validate_analysis` & `SuggestionWorker.process` reject unknown code (`ai_service_unavailable`), and `order_context` parity verified (`6` refunded / `4` non-refunded vs `10` allowed in `ORDER_CONTEXT_ALLOWED_FIELDS`). |

---

## 3. Residual Notes & Open Workstreams

- **Frontend UI note (lower priority, API secure):** `apps/frontend/src/features/console.tsx:85-86` computes `canSendReply = can('send_reply') || (!readOnly && (hasAuthority || !ticket.is_authority_required))`. When a ticket's `allowed_actions` is `[]` (such as promoted self-approval `awaiting_approval`), `readOnly=true` hides the action cleanly, though on non-`readOnly` states (`pending` with `correct_intent`/`escalate`) the fallback depends on `replyBlocker` or backend `403`.
- **Methodological boundary:** Dynamic constructor tests (`19` frozen matrix cases + `46` backend + `5` frontend tests) exercise bounded synthetic scenarios and typed HTTP fault mocks without claiming 100% path coverage across the whole system.
- **Explicitly OPEN (not part of Gap 2):**
  - **Gap 3 (NER / Privacy Leakage Guard):** Remains **OPEN** — ready for sequential coordinator assignment to Worker A (implementation only, **NO training**, `2/2 STOP` intact).
  - **`Engine` `order_context` field parity (`6 vs 10`):** Remains **OPEN** — `apps/backend/tickets/service.py:38-44` emits `4` base + `2` refund fields (`6`), omitting `placed_at`, `estimated_delivery_at`, `delivered_at`, and `refund_requested_at` listed in `ORDER_CONTEXT_ALLOWED_FIELDS` (`apps/core_backend/llm/gemini.py:418-429`).
