# Task A Review Audit — `guard_corrections_20261113` Strict Mismatches, Defect Separation & Acceptance Decisions

**Dispatch:** `ctx_1acc6818f3d1` (`task_bf14e9b4a110`)  
**Reviewed Commits:** Stage A `85aa931` + Stage B `eb85d0d` + Stage C `4c25072`  
**Policy & Spec Anchors:** [`docs/CHỦ ĐỀ 1.md`](../../../docs/CHỦ ĐỀ 1.md), [`data/benchmarks/system/v2/acceptance/cases.jsonl`](../../../data/benchmarks/system/v2/acceptance/cases.jsonl), C [`guard_corrections_20261113`](../../../../../../Năm%203/SD/project/SupportIQ/artifacts/evaluation/guard_corrections_20261113/GUARD_CORRECTIONS_REPORT.md) (`0` live calls, `0` production edits).

---

## 1. Executive Accounting of the 23 Fault Executions

Across C's post-fix verification (`11` primary + `12` companion executions, `23/23` `no_draft_preserved=True`, `0` live HTTP requests):
- **`8 STRICT_PASS`** (`2` primary runtime `encoder_failure`; `6` companion `ml_error`, `encoder_unavailable`, and offline `llm_timeout`).
- **`15` Strict Mismatches** (`13 SAFE_FALLBACK_MISMATCH` + `2 INTAKE_DENIAL_404_MISMATCH`), decomposing cleanly into:
  - **`1` real cross-surface implementation defect (`DEFECT-B1`, also affected by harness cross-mapping):** `backend_pg_encoder_unavailable`, where `apps/ai_service/engine.py` (`eb85d0d`) retained legacy `abstained` + `"no_valid_document"` on `encoder_unavailable`, violating the coordinator-confirmed escalation agreement (`msg_27ccb3d2b022`, `msg_d11e5e635e37`) and diverging from `PipelineRunner` (`escalate`).
  - **`5` contradictory / cross-mapped fixture or harness rows:** `3` contradictory `ml_timeout` rows (`must_escalate=True` alongside `expected.actions=["escalate","clarify","manual_fallback"]`), `1` frozen-empty-slot fixture (`unc-track_order-06` `pipeline_runner_commerce_not_found_frozen_empty_slots`), and `1` clean `PipelineRunner` row (`pipeline_runner_encoder_unavailable`) cross-mapped under `unc-return_policy-04` (`reason_any=["encoder_failure"]`).
  - **`5` security/classifier architectural behaviors (non-defects):** `2` Backend HTTP `404` privacy denials (`ORD-1002`, `ORD-9999`) with `0` tickets created, `2` text-only fail-closed routes (`out_of_scope_intent` / `low_confidence`), and `1` `PipelineRunner` real-classifier early scope escalation (`customer_service` on `"customer cust_1"`).
  - **`4` pure canonical reason-code alias mismatches:** `commerce_unauthorized_customer` vs `commerce_unauthorized` (`1` row), `commerce_order_not_found` vs `commerce_not_found` (`1` row), and `grounding_failed` vs `llm_invalid_citations` (`2` rows).

*(Exact accounting: `1 + 5 + 5 + 4 = 15` non-`STRICT_PASS` rows + `8 STRICT_PASS` = `23` total executions.)*

---

## 2. Row-by-Row Separation: Real Defects vs. Contradictory Fixtures vs. Security/Naming

### 2.1 ML Timeout Manual Fallback (`unc-track_order-03`, `ml_timeout`) — 3 `SAFE_FALLBACK_MISMATCH`
- **Rows:** `backend_pg_analysis_read_timeout`, `backend_pg_model_timeout_error` (`raw=unavailable` -> `manual_fallback`, `['ai_service_unavailable', 'ml_timeout']`, `failure_code='ml_timeout'`, `allowed_actions=['retry_suggestion', 'submit_reply_proposal', 'escalate', 'send_reply']`), `pipeline_runner_ml_read_timeout` (`manual_fallback`, `['ml_unavailable', 'ml_timeout']`).
- **Diagnosis (Contradictory Frozen Fixture, NOT an implementation defect):**
  - Frozen `data/benchmarks/system/v2/acceptance/cases.jsonl` `unc-track_order-03` has an internal contradiction: `"expected": {"actions": ["escalate", "clarify", "manual_fallback"], "reason_any": ["ml_timeout"], "must_escalate": true}` — simultaneously allowing `"manual_fallback"` in `actions` while setting `must_escalate: true`. Companion `unc-track_order-04` (`ml_error`) uses `"must_escalate": false` with the identical schema and passes `STRICT_PASS`.
  - Under `docs/CHỦ ĐỀ 1.md` **FR-05** (*"abstention/fallback/escalation"*), **Section 4 `System reliability`**, and **Section 6 `Initial Risks & Required Controls`** (*"Timeout/error handling, fallback sang quy trình thủ công"*), transient ML timeouts are recoverable operational outages suited for **manual fallback + retry**, not specialist policy escalation.
  - Furthermore, `apps/backend/tickets/service.py:71` (`allowed_actions`) only grants `retry_suggestion` when `draft_status in ("unavailable", "llm_unavailable")`; coercing ML timeout to `escalation_recommended` would disable staff AI retry.
- **Acceptance Decision:** **ACCEPT `manual_fallback` (`unavailable` on Backend, `manual_fallback` on `PipelineRunner`) with `"ml_timeout"` present and `0` LLM calls.** Record `unc-track_order-03`'s `must_escalate=True` as a frozen-fixture contradiction rather than patching production code to escalate timeouts.

### 2.2 `encoder_unavailable` Fallback vs. Escalation (`unc-return_policy-04` vs `unc-return_policy-03`) — 2 `SAFE_FALLBACK_MISMATCH`
- **Rows:**
  - `unc-return_policy-04` `backend_pg_encoder_unavailable`: `raw=abstained` (`manual_fallback`), `reason_codes=['encoder_unavailable', 'insufficient_evidence', 'no_valid_document']` (`strict_must_escalate_matched=False`, `strict_reason_any_matched=False`).
  - `unc-return_policy-04` `pipeline_runner_encoder_unavailable`: `raw=escalate`, `reason_codes=['insufficient_evidence', 'encoder_unavailable']` (`strict_must_escalate_matched=True`, `strict_reason_any_matched=False`).
- **Diagnosis (1 Real Defect + 1 Harness Cross-Mapping):**
  1. **Real Implementation Defect (`DEFECT-B1`, `apps/ai_service/engine.py:142-187` in `eb85d0d`):** Despite the coordinator-confirmed agreement (`msg_27ccb3d2b022`, `msg_d11e5e635e37`) requiring `Engine._analyse()` to escalate `encoder_unavailable` with `["insufficient_evidence", "encoder_unavailable"]` without collapsing to `"no_valid_document"`, `engine.py:143` kept `# Preserve legacy abstained/no_valid_document contract (test_escalation_12) while tagging encoder_unavailable` (`tests/e2e/test_full_pipeline.py:446-452`) and omitted `is_encoder_unavailable` from `recommendation = "escalate"` (`engine.py:174-187`). This leaves **Engine (`abstained`) out of parity with `PipelineRunner` (`escalate`)** — hidden in companion `unc-return_policy-03` only because `unc-return_policy-03` has `must_escalate: false`.
  2. **Harness Cross-Mapping Artifact:** Injecting `encoder=None` (`encoder_unavailable`) under `unc-return_policy-04` (`fault="encoder_failure"`, `reason_any=["encoder_failure"]`) fails `reason_any` even when `PipelineRunner` behaves cleanly (`unc-return_policy-03` is the canonical `encoder_unavailable` case). Keeping `encoder_unavailable` distinct from `encoder_failure` satisfies `FR-07`/`FR-08` diagnosability.
- **Acceptance Decision:**
  - **Flag `DEFECT-B1` (`Engine` vs `PipelineRunner` `encoder_unavailable` parity) explicitly for coordinator disposition:** recommend either (a) a targeted follow-up updating `Engine._analyse` + `test_escalation_12_retrieval_unavailable` to match the agreed `escalation_recommended` (`["insufficient_evidence", "encoder_unavailable"]`) contract, **or** (b) an explicit coordinator waiver accepting `abstained` (`manual_fallback`, `no_draft=True`) as legacy `test_escalation_12` compatibility while documenting cross-surface divergence. Do **not** merge assuming `Engine` implemented the agreed escalation.
  - **Accept `PipelineRunner` `encoder_unavailable -> escalate` with `['insufficient_evidence', 'encoder_unavailable']`** and attribute `unc-return_policy-04` `*_encoder_unavailable` `reason_any` mismatch to testing an `encoder_unavailable` injection against an `encoder_failure` fixture.

### 2.3 Commerce `404` Privacy vs. Ticket Expectations (`unc-track_order-05`, `unc-track_order-06`) — 2 `INTAKE_DENIAL_404_MISMATCH` + 6 `SAFE_FALLBACK_MISMATCH`
- **Explicit `order_id` HTTP Intake (`backend_pg_explicit_unauthorized_order`, `backend_pg_explicit_not_found_order`):**
  - `POST /v1/shop/tickets` calls `require_order(session, order_id, actor.customer_id)` (`apps/backend/commerce/service.py:8-12`, `apps/backend/tickets/service.py:138`), returning HTTP **`404`** (`urn:supportiq:problem:not-found`, `tickets_created_delta = 0`, `llm_calls = 0`) uniformly for another customer's `ORD-1002` and nonexistent `ORD-9999`.
  - This directly implements `docs/CHỦ ĐỀ 1.md` **FR-08** (*"phân quyền người dùng phù hợp và bảo vệ dữ liệu"*) and **Section 6** (*"Rủi ro bảo mật và quyền riêng tư"*), preventing IDOR ticket binding and order-existence enumeration (`403` vs `404`). The frozen `cases.jsonl` rows (`reason_any=["commerce_unauthorized"]`, `must_escalate=true` for `05`; `["commerce_not_found"]` for `06`) describe post-intake `PipelineRunner` slot evaluation, not Backend ticket admission control.
  - **Acceptance Decision:** **ACCEPT HTTP `404` (`0` tickets created) on explicit `order_id` intake as a non-negotiable security control.** Do not alter `require_order` to satisfy frozen AI-pipeline fixtures.
- **Text-Only Backend Intake (`backend_pg_text_only_unauthorized_order`, `backend_pg_text_only_not_found_order`):**
  - `create_ticket` (`apps/backend/tickets/service.py:131-136`) binds `order_id` solely against orders owned by `actor.customer_id`. Because `ORD-1002` (owned by `cust-1002`) and `ORD-9999` are not owned by `customer-1`, `ticket.order_id` stays `None` (`order_context={}`). Both fail closed cleanly without data leakage (`customer_service` -> `escalation_recommended` `['out_of_scope_intent']` on `ORD-1002`; low-confidence `abstained` `['low_confidence', 'out_of_scope_intent']` on `ORD-9999`).
  - **Acceptance Decision:** **ACCEPT safe fail-closed behavior (`0` drafts, `0` leaked order details).** Note explicitly that text-only Backend intake will never emit `commerce_unauthorized` / `commerce_not_found` because ownership filtering precedes AI invocation.
- **`PipelineRunner` (`pipeline_runner_real_classifier_commerce_unauthorized`, `pipeline_runner_track_order_commerce_unauthorized`, `pipeline_runner_commerce_not_found_frozen_empty_slots`, `pipeline_runner_commerce_not_found_explicit_slot`):**
  - `pipeline_runner_commerce_not_found_frozen_empty_slots` fails strictly due to a **contradictory frozen fixture**: `cases.jsonl` `unc-track_order-06` text mentions `ORD-9999`, yet sets `"extracted_slots": {}`, triggering `Gate 6` `clarify` (`['missing_order_id']`, compliant with `expected.actions` and `must_escalate=False`) before reaching `CommerceAdapter`.
  - `pipeline_runner_real_classifier_commerce_unauthorized` predicts `customer_service` on `"Track order ORD-1002 for customer cust_1"`, escalating at `Gate 2c` (`recognized_outside_product_scope`) prior to Step 4 `CommerceAdapter`. Both safety (`escalate`, `0` drafts) and zero leak hold.
  - `pipeline_runner_track_order_commerce_unauthorized` and `pipeline_runner_commerce_not_found_explicit_slot` already reach `CommerceAdapter` and **escalate cleanly** (`['commerce_unauthorized_customer']`, `['commerce_order_not_found']`) — differing only by reason-code naming below.

### 2.4 Canonical Reason Aliases (Commerce, Post-Generation Grounding, Encoder)
| Subsystem / Frozen Code | Runtime Code Emitted | Cause & Source Location | Proposed Acceptance & Normalization Rule |
|---|---|---|---|
| `commerce_unauthorized` (`unc-track_order-05`) | `commerce_unauthorized_customer` | `CommerceAdapter.lookup_order` (`adapter.py:38`) + `PipelineRunner` (`pipeline_runner.py:100`) prepend `"commerce_"` | **ACCEPT subtype alias** now; in future cleanup emit `["commerce_unauthorized", "commerce_unauthorized_customer"]` (or `commerce_unauthorized_scope`) so both canonical and fine-grained codes exist. |
| `commerce_not_found` (`unc-track_order-06`) | `commerce_order_not_found` | `CommerceAdapter.lookup_order` (`adapter.py:33`) + `PipelineRunner` (`pipeline_runner.py:100`) | **ACCEPT alias** now; emit `["commerce_not_found", "commerce_order_not_found"]` if harmonized later. |
| `llm_invalid_citations` (`unc-cancel_order-03`) | `grounding_failed` | `validate_generated_draft` (`safety.py`) and `Engine.draft` (`engine.py:224,291`) normalize invalid citations to `grounding_failed`; `AI_REASONS` (`jobs.py:29`) accepts `grounding_failed` (not `llm_invalid_citations`) | **CANONICALIZE on `grounding_failed`** (accept `grounding_failed` as satisfying frozen `llm_invalid_citations`); `llm_invalid_citations` stays an internal `GeminiDraftClient` exception code (`LLMError.code`). |
| `encoder_failure` vs `encoder_unavailable` | `encoder_failure` + `encoder_failed` vs `encoder_unavailable` | `RetrievalAdapter` (`adapter.py`) separates `encoder=None` vs `search_policies` failure | **KEEP DISTINCT:** `encoder_unavailable` != `encoder_failure` (backward-compat alias `encoder_failed` retained). |

---

## 3. Summary Disposition Matrix for Root Integration

1. **Accept without production edits (contradictory fixture / security control / canonical alias):**
   - `unc-track_order-03` (`ml_timeout` -> `manual_fallback` with `ml_timeout`, `0` drafts, retryable).
   - `unc-track_order-05` & `unc-track_order-06` explicit Backend `404` (`0` tickets created) & text-only fail-closed routes.
   - `unc-track_order-06` `PipelineRunner` empty-slot `clarify` (`missing_order_id` fixture defect).
   - Canonical reason aliases: `commerce_unauthorized_customer -> commerce_unauthorized`, `commerce_order_not_found -> commerce_not_found`, `grounding_failed -> llm_invalid_citations`.
2. **Require explicit coordinator disposition (real defect / open parity gap):**
   - **`DEFECT-B1` (`apps/ai_service/engine.py:142-187`):** Worker B retained `abstained` + `"no_valid_document"` on `encoder_unavailable` (`test_escalation_12`), leaving `Engine` and `PipelineRunner` (`escalate`) non-equivalent and diverging from coordinator-approved contract `msg_d11e5e635e37`. Either file a targeted B follow-up updating `Engine._analyse` + `test_escalation_12`, or record a formal coordinator waiver retaining legacy `abstained` on `Engine`.
