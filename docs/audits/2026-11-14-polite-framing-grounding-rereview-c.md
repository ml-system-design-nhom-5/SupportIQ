# Stage 1 Re-Review — Corrective Grounding Fix (`d8966538`)

- **Reviewer:** Worker C (`task_7d6808ca6f99`)
- **Reviewed Commit:** `d896653803cd6f4d8dad307b209b3671ceaddfe0` (`fix(engine,safety): route Engine.draft through shared sentence-level grounding validation`)
- **Prior Baseline / Review:** `docs/audits/2026-11-14-polite-framing-grounding-b.md`, `docs/audits/2026-11-14-polite-framing-grounding-review-c.md` (`b88692ccacda54c3e7ba07162e48e11abc7c7cb9`)
- **Verdict:** **`CHANGES_REQUIRED`**
- **Stage 2 Gate Status:** **HALTED after Stage 1.** Per the sequential gate, Stage 2 fixed model evaluation of `fit2-taxonomy-audit-v5-r2` (`0b2d26c2...`, `ca3d711c...`) was **not** executed because Stage 1 re-review reproduced remaining grounding/ownership defects across `apps/core_backend/safety.py` and `apps/ai_service/engine.py`.

---

## 1. Prior Findings Disposition & Passing Checks

- **Resolved from `b88692c`:**
  - Blanket `len(paragraph) <= 40` exemption and paragraph-level `not source_ids` skip removed from `Engine.draft()` (`apps/ai_service/engine.py:259-295`).
  - All prior short uncited bypasses (`"Shipping is free."`, `"Your order is cancelled."`, `"We approved your return."`, `"You are eligible."`, `"No charge applies."`, `"It will arrive tomorrow."`, `"Hello, you get a free gift!"`), `[S1]; ...`, `[S1].Next`, newline splits, `[s1]`, `[S1, S2]`, and uncited clarification questions with `is_clarification=False` now fail with `llm_unavailable` / `grounding_failed` (`viol="uncited_claim"`).
  - Clarification gating (`_SAFE_CLARIFICATION_QUESTION` with `allow_clarification_questions=bool(generated.get("is_clarification", False))`) rejects `"Is shipping free?"`, `"Could you provide your order ID?"` without any `[S1]` (`viol="invalid_citations"`), and clarification questions carrying `$5` / `3 days` / `"refund you"` commitments.
  - Legitimate polite topic framing + `[S1]` policy + `[S2]` `order_facts` (both single-`field` legacy and multi-`fields` new schemas, `0 VND`, ISO dates, customer-present `[NAME_1]`, unpermitted `[PHONE_1]` PII guard -> `llm_invalid_output`) work as expected.
- **Focused Pytest Suite Observed on `d8966538`:**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_llm.py tests/unit/test_ai_grounding.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_order_context_grounding.py tests/unit/test_pipeline_runner_safety_b.py tests/unit/test_retrieval_grounding_b2.py tests/application/test_application.py tests/application/test_backend_safety_closure.py tests/e2e/test_full_pipeline.py -q`
  - Result: **`226 passed in 107.21s (0:01:47)`** (regression gaps below are uncovered by these suites).

---

## 2. Remaining Blocking Findings (`CHANGES_REQUIRED`)

### Finding 1 (High) — Bare present-tense passive status claims bypass `_PASSIVE_COMMIT` and slip through numeric checks
- **Location:** `apps/core_backend/safety.py:479-484`
- **Defect:** `_PASSIVE_COMMIT` uses `is\s+(?:now|already)` instead of `is(?:\s+(?:now|already))?`. As a result, present-tense passive transaction/status commitments (`is cancelled`, `is approved`, `is refunded`, `is credited`, `is reimbursed`, `is processed`) fail to match `has_ungrounded_transaction_commitment()`.
- **Observed Reproduction (both `Engine.draft()` and `GeminiDraftClient.generate()` + `find_draft_grounding_violation()`):**
  - `"Your order is cancelled [S1]."` against `order_facts` (`order_status: delivered`) or `POL-RET-001` (`30 days`) -> `engine=draft_ready`, `viol=None`, `gemini=ALLOWED`
  - `"Your refund is approved [S1]."` against `POL-RET-001` or `order_facts` (`order_status: delivered`, `refund_status: pending`) -> `engine=draft_ready`, `viol=None`, `gemini=ALLOWED`
  - `"Your return is approved [S1]."` against `POL-RET-001` or `order_facts` (`order_status: delivered`, `return_status: requested`) -> `engine=draft_ready`, `viol=None`, `gemini=ALLOWED`
  - `"Your refund is refunded [S1]."`, `"Your return is processed [S1]."`, `"Your order is credited [S1]."` against `POL-RET-001` -> all `engine=draft_ready`, `viol=None`, `gemini=ALLOWED`
- **Required Fix:** Make `(?:now|already)` optional after `is` (`is(?:\s+(?:now|already))?`) and cover `return_status` / approval status checks in `_is_verified_recorded_order_status()` against retrieved `order_facts` only.

### Finding 2 (High) — Self-referential `input_snapshot` in `Engine.draft()` allows forged policy docs and contradicting `order_facts` (kept for e2e fixture compatibility)
- **Location:** `apps/ai_service/engine.py:259-320`; `apps/core_backend/safety.py:744`; noted in `docs/audits/2026-11-14-polite-framing-grounding-b.md:25`
- **Defect:** Unlike `pipeline_runner.py:149-165` (which passes trusted `prepare_llm_input(..., evidence_list, order_facts)["sources"]` into `validate_generated_draft()`), `Engine.draft()` validates `raw_sources = generated["input_snapshot"]["sources"]` **against itself** without checking retrieved `evidence` ownership or `request.get("order_context")` values. Non-empty `source_type` / `document_id` / `version` metadata checks do not prove retrieved source or field-value ownership.
  - Per `b`'s audit note (`line 25`), document ID verification was omitted in part to avoid breaking `tests/e2e/test_full_pipeline.py::test_normal_shipping_cost_flow`, where `adapter.retrieve` returns `b1000000-...-0001` while `mock_llm.generate` returns `b1000000-...-0005` (and omits `"citations"`).
  - Additionally, `Engine.draft()` accepts `src_type in ("order_facts", "order", "order_context")` (`engine.py:308`), whereas `find_draft_grounding_violation()` treats only `source_type == "order_facts"` as order sources (`safety.py:744`).
- **Observed Reproduction:**
  - `forged_policy_not_in_evidence`: `MockLLM` returning `POL-FABRICATED` (`version=99`, `"Everything is free forever."`) not in retrieved `evidence` -> `Engine.draft()` returns `draft_ready`.
  - `forged_snapshot_and_citations`: `MockLLM` returning matching forged `"citations"` + `"input_snapshot"` (`POL-FORGED`, `"Your refund is approved."`) -> `Engine.draft()` returns `draft_ready`.
  - `forged_order_facts_contradicts_ctx`: `request["order_context"] = {"order_status": "delivered"}`, `MockLLM` returning `source_type="order_facts"` with `excerpt="order_status: cancelled\nshipping_cost: 0 VND"` and `"Your order has been cancelled with 0 VND shipping [S1]."` -> `Engine.draft()` returns `draft_ready` citing `fields=['order_status']`.
  - **Non-numeric claim scope note:** `find_draft_grounding_violation()` enforces numeric/date support, transaction commitments, and cosmetics/duplicate-charge guardrails, not general non-numeric entailment (`"We include free overnight drone courier globally [S1]."` against `POL-RET-001` -> `engine=draft_ready`, `viol=None`), making source-ownership verification in `Engine.draft()` critical so arbitrary excerpts cannot be injected under `S1`.
- **Required Fix:** Verify `policy` `(document_id, version, excerpt)` against retrieved `evidence` (updating stale mock retriever/LLM alignment in `tests/e2e/test_full_pipeline.py::test_normal_shipping_cost_flow` rather than weakening `Engine.draft()`), validate `order_facts` key/value provenance against `supplied_facts`, and unify allowed order `source_type` handling (`order_facts`) across `engine.py` and `safety.py`.

### Finding 3 (Medium) — Missing-space period without prior `[S1]` and inline clause splices evade `split_draft_sentences`
- **Location:** `apps/core_backend/safety.py:367-370, 502-520`
- **Defect:** `_SENTENCE_BOUNDARY` splits `.` without trailing whitespace only after `]` (`[S1].Next`), not `.Next` when the first sentence is uncited (`Shipping is free.Products ... [S1].`).
- **Observed Reproduction:**
  - `"Shipping is free.Products may be returned within 30 days in original packaging [S1]."` -> `split_draft_sentences` returns `1` sentence, `Engine.draft() -> draft_ready`, `find_draft_grounding_violation() -> None`, `GeminiDraftClient.generate() -> ALLOWED`.
  - *(Also observed: clause splices sharing `[S1]` such as `"Products may be returned within 30 days in original packaging [S1], shipping is free."` and `"Shipping is free, products may be returned within 30 days in original packaging [S1]."` remain single sentences and return `engine=draft_ready`, `viol=None`, `gemini=ALLOWED`.)*
- **Required Fix:** Handle missing-space sentence boundaries `.` before alphabetic sentence starts (while preserving `_ABBREVIATION_PREFIX` and decimals) and guard clause-spliced uncited factual claims sharing `[S1]` across `,` / `:` / ` - ` / `( ... )`.

---

## 3. Gate Decision

Hold **Stage 2 evaluation of `fit2-taxonomy-audit-v5-r2`** until Findings 1–3 are resolved, regression tests are added in `tests/unit/test_ai_grounding.py` and `tests/unit/test_gemini_llm.py`, and Stage 1 re-review returns `PASS`.
